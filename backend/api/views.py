from django.shortcuts import render
from django.contrib.auth import authenticate
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from rest_framework import status, viewsets, permissions
from rest_framework.decorators import api_view, permission_classes, action
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.token_blacklist.models import OutstandingToken, BlacklistedToken
from api.services.mongo_service import mongo_service
from api.services.user_service import user_service
from bson import ObjectId
from datetime import datetime
from django.http import Http404
import logging
from django.core.cache import cache
from django.conf import settings
import json

from .serializers import TranscriptSerializer, QuestionSerializer
from .youtube_utils import get_transcript, format_transcript, extract_video_id
from api.services.qa_service import qa_service
from qa_engine.qa_model import qa_model  # Add this import

from qa_engine.deepseek_utils import deepseek_query  # Your existing Deepseek integration
from datetime import datetime

# Create your views here.

logger = logging.getLogger(__name__)

@api_view(['POST'])
@permission_classes([AllowAny])
def signup(request):
    email = request.data.get('email')
    password = request.data.get('password')
    first_name = request.data.get('first_name', '')
    last_name = request.data.get('last_name', '')

    # Validate required fields
    if not email or not password:
        return Response(
            {'error': 'Email and password are required'}, 
            status=status.HTTP_400_BAD_REQUEST
        )

    # Validate email format
    try:
        validate_email(email)
    except ValidationError:
        return Response(
            {'error': 'Invalid email format'}, 
            status=status.HTTP_400_BAD_REQUEST
        )

    # Check if email already exists
    if user_service.user_exists(email):
        return Response(
            {'error': 'Email already registered'}, 
            status=status.HTTP_400_BAD_REQUEST
        )

    try:
        # Create user in MongoDB
        user = user_service.create_user(
            email=email,
            password=password,
            first_name=first_name,
            last_name=last_name
        )
        
        # Create JWT tokens
        refresh = RefreshToken()
        refresh['user_id'] = user['id']
        refresh['email'] = user['email']
        
        return Response({
            'message': 'User created successfully',
            'access': str(refresh.access_token),
            'refresh': str(refresh),
            'user': {
                'email': user['email'],
                'first_name': user['first_name'],
                'last_name': user['last_name']
            }
        }, status=status.HTTP_201_CREATED)
    except Exception as e:
        return Response(
            {'error': str(e)}, 
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

@api_view(['POST'])
@permission_classes([AllowAny])
def login(request):
    email = request.data.get('email')
    password = request.data.get('password')

    if not email or not password:
        return Response(
            {'error': 'Email and password are required'}, 
            status=status.HTTP_400_BAD_REQUEST
        )

    try:
        # Get user by email
        user = user_service.get_user_by_email(email)
        if not user:
            return Response(
                {'error': 'Invalid credentials'}, 
                status=status.HTTP_401_UNAUTHORIZED
            )
        
        # Verify password
        if user_service.verify_password(user, password):
            # Update last login
            user_service.update_last_login(user['id'])
            
            # Create JWT tokens
            refresh = RefreshToken()
            refresh['user_id'] = user['id']
            refresh['email'] = user['email']
            
            return Response({
                'message': 'Login successful',
                'access': str(refresh.access_token),
                'refresh': str(refresh),
                'user': {
                    'email': user['email'],
                    'first_name': user['first_name'],
                    'last_name': user['last_name']
                }
            }, status=status.HTTP_200_OK)
        else:
            return Response(
                {'error': 'Invalid credentials'}, 
                status=status.HTTP_401_UNAUTHORIZED
            )
    except Exception as e:
        return Response(
            {'error': str(e)}, 
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def logout(request):
    try:
        refresh_token = request.data.get('refresh')
        if not refresh_token:
            return Response({'error': 'Refresh token is required'}, status=status.HTTP_400_BAD_REQUEST)
            
        token = RefreshToken(refresh_token)
        token.blacklist()
        
        return Response({'message': 'Successfully logged out'}, status=status.HTTP_200_OK)
    except Exception as e:
        return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

class TranscriptViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = TranscriptSerializer

    def get_queryset(self):
        user_id = getattr(self.request, 'user_id', None)
        if not user_id:
            return []
            
        # Check if we should filter favorites only
        favorites_only = self.request.query_params.get('favorite', '').lower() == 'true'
        
        # Get transcripts from MongoDB and convert ObjectIds to strings
        query = {'user_id': str(user_id)}
        if favorites_only:
            query['is_favorite'] = True
            
        transcripts = list(mongo_service.db.transcripts.find(query))
        for transcript in transcripts:
            transcript['id'] = str(transcript['_id'])
        return transcripts

    def get_object(self):
        pk = self.kwargs.get('pk')
        user_id = getattr(self.request, 'user_id', None)
        
        # Try to find transcript by video_id first
        transcript = mongo_service.db.transcripts.find_one({
            'video_id': pk,
            'user_id': str(user_id)
        })
        
        # If not found, try as ObjectId (for backwards compatibility)
        if not transcript:
            try:
                transcript = mongo_service.db.transcripts.find_one({
                    '_id': ObjectId(pk),
                    'user_id': str(user_id)
                })
            except:
                pass
                
        if not transcript:
            raise Http404("Transcript not found")
            
        transcript['id'] = str(transcript['_id'])
        return transcript

    def destroy(self, request, *args, **kwargs):
        """Delete a transcript and its associated questions"""
        try:
            user_id = getattr(request, 'user_id', None)
            if not user_id:
                return Response(
                    {'error': 'Authentication failed - no user ID found'},
                    status=status.HTTP_401_UNAUTHORIZED
                )

            transcript_id = kwargs.get('pk')
            success = mongo_service.delete_transcript(transcript_id, str(user_id))
            
            if not success:
                return Response(
                    {'error': 'Transcript not found'},
                    status=status.HTTP_404_NOT_FOUND
                )
                
            return Response(status=status.HTTP_204_NO_CONTENT)
            
        except Exception as e:
            return Response(
                {'error': f'Failed to delete transcript: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @action(detail=False, methods=['post'], url_path='create-from-video')
    def create_from_video(self, request):
        logger.info("Starting transcript creation process")
        
        # Check if user is authenticated and has user_id
        user_id = getattr(request, 'user_id', None)
        if not user_id:
            logger.error("No user_id found in request")
            return Response(
                {'error': 'Authentication failed - no user ID found'},
                status=status.HTTP_401_UNAUTHORIZED
            )
            
        video_url = request.data.get('video_id')  
        logger.info(f"Received video URL: {video_url}")
        
        if not video_url:
            logger.error("No video URL provided")
            return Response({'error': 'Video URL is required'}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            # Extract video ID from URL
            logger.info("Attempting to extract video ID")
            video_id = extract_video_id(video_url)
            logger.info(f"Extracted video ID: {video_id}")
            
            if not video_id:
                logger.error("Failed to extract valid video ID from URL")
                return Response({'error': 'Invalid YouTube URL'}, status=status.HTTP_400_BAD_REQUEST)

            # Check if transcript already exists
            logger.info(f"Checking for existing transcript for user {user_id} and video {video_id}")
            existing_transcript = mongo_service.get_transcript_by_user_and_video(
                user_id=str(user_id),
                video_id=video_id
            )

            if existing_transcript:
                logger.info("Found existing transcript")
                return Response(
                    {
                        'error': 'A transcript for this video already exists',
                        'transcript': existing_transcript
                    },
                    status=status.HTTP_400_BAD_REQUEST
                )

            # Try to get transcript from cache first
            cache_key = f'transcript_{video_id}'
            cached_data = cache.get(cache_key)
            
            if cached_data:
                logger.info("Found transcript in cache")
                transcript_data, language = cached_data
            else:
                # Get transcript from YouTube
                logger.info("Attempting to fetch transcript from YouTube")
                transcript_data, language = get_transcript(video_id)
                logger.info(f"Successfully fetched transcript in {language}")
                
                # Cache the transcript
                cache.set(cache_key, (transcript_data, language), settings.TRANSCRIPT_CACHE_TIMEOUT)
            
            formatted_transcript = format_transcript(transcript_data)
            logger.info(f"Formatted transcript length: {len(formatted_transcript)}")
            
            # Process transcript with DeepSeek
            logger.info("Processing transcript with DeepSeek")
            try:
                processed_data = qa_model.process_transcript(formatted_transcript)
                logger.info("Successfully processed transcript with DeepSeek")
                logger.debug(f"Processed data structure: {list(processed_data.keys())}")
            except Exception as e:
                logger.error(f"Failed to process transcript with DeepSeek: {str(e)}")
                logger.error(f"Formatted transcript preview: {formatted_transcript[:200]}...")
                raise ValueError("Failed to process transcript with DeepSeek")
            
            # Save processed transcript to MongoDB
            logger.info("Attempting to save processed transcript to MongoDB")
            try:
                result = mongo_service.save_transcript(
                    user_id=str(user_id),
                    video_id=video_id,
                    content=processed_data['punctuated_text'],
                    language=language,
                    translation=processed_data['translation'],
                    vocabulary=processed_data['vocabulary']
                )
                logger.info("Successfully saved processed transcript to MongoDB")
            except KeyError as ke:
                logger.error(f"Missing key in processed data: {str(ke)}")
                logger.error(f"Processed data keys: {list(processed_data.keys())}")
                raise ValueError(f"Invalid response format from DeepSeek: missing {str(ke)}")
            except Exception as e:
                logger.error(f"Failed to save transcript to MongoDB: {str(e)}")
                raise
            
            # Return the saved transcript data
            saved_transcript = {
                'id': str(result.inserted_id),
                'video_id': video_id,
                'title': request.data.get('title', 'Untitled'),
                'content': processed_data['punctuated_text'],
                'language': language,
                'user_id': str(user_id),
                'translation': processed_data['translation'],
                'vocabulary': processed_data['vocabulary']
            }
            
            logger.info("Successfully completed transcript creation and processing")
            return Response(saved_transcript, status=status.HTTP_201_CREATED)
            
        except ValueError as e:
            logger.error(f"ValueError in transcript creation: {str(e)}")
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logger.error(f"Unexpected error in transcript creation: {str(e)}")
            import traceback
            logger.error(f"Full traceback: {traceback.format_exc()}")
            return Response(
                {
                    'error': 'An error occurred while processing the transcript',
                    'detail': str(e)
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @action(detail=True, methods=['post'])
    def toggle_favorite(self, request, pk=None):
        try:
            # Toggle favorite in MongoDB
            result = mongo_service.toggle_transcript_favorite(
                transcript_id=pk,
                user_id=str(request.user_id)
            )
            if result:
                return Response({
                    'id': str(result['_id']),
                    'is_favorite': result['is_favorite']
                })
            return Response(
                {'error': 'Transcript not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            return Response(
                {'error': f'Failed to toggle favorite status: {str(e)}'},
                status=status.HTTP_400_BAD_REQUEST
            )

    @action(detail=True, methods=['post'], url_path='process')
    def process_transcript(self, request, pk=None):
        """Process transcript with DeepSeek for punctuation and translation"""
        try:
            transcript = self.get_object()
            if not transcript:
                return Response(
                    {'error': 'Transcript not found'},
                    status=status.HTTP_404_NOT_FOUND
                )

            # Check if already processed
            if transcript.get('processed_content'):
                return Response(
                    {'error': 'Transcript already processed'},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # Prepare prompt for DeepSeek
            prompt = f"""Please process the following Hindi text:
            1. Add proper punctuation (।, ?, !, etc.)
            2. Provide an English translation
            3. Identify and explain important vocabulary words

            Return ONLY a JSON object with the following structure:
            {{
                "punctuated_text": "punctuated Hindi text",
                "translation": "English translation",
                "vocabulary": [
                    {{
                        "word": "Hindi word",
                        "meaning": "English meaning",
                        "example": "Example sentence"
                    }}
                ]
            }}

            Hindi Text:
            {transcript['content']}"""

            # Call DeepSeek API
            response = deepseek_query(prompt)
            
            try:
                # Parse the response
                processed_data = json.loads(response)
                
                # Update transcript in MongoDB
                mongo_service.db.transcripts.update_one(
                    {'_id': ObjectId(pk)},
                    {
                        '$set': {
                            'processed_content': processed_data,
                            'updated_at': datetime.utcnow()
                        }
                    }
                )
                
                return Response(processed_data, status=status.HTTP_200_OK)
                
            except json.JSONDecodeError:
                return Response(
                    {'error': 'Failed to parse DeepSeek response'},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )
                
        except Exception as e:
            logger.error(f"Error processing transcript: {str(e)}")
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

class QuestionViewSet(viewsets.ModelViewSet):
    serializer_class = QuestionSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        transcript_id = self.kwargs.get('transcript_pk')
        # Fetch questions from MongoDB
        questions = list(mongo_service.db.qa_pairs.find({
            'transcript_id': transcript_id
        }))
        for question in questions:
            question['_id'] = str(question['_id'])
        return questions

    def get_object(self):
        question_id = self.kwargs.get('pk')
        transcript_id = self.kwargs.get('transcript_pk')
        
        # Get question from MongoDB
        question = mongo_service.db.qa_pairs.find_one({
            '_id': ObjectId(question_id),
            'transcript_id': transcript_id
        })
        
        if not question:
            raise Http404("Question not found")
            
        question['_id'] = str(question['_id'])
        return question

    @action(detail=False, methods=['post'])
    def generate(self, request, transcript_pk=None):
        try:
            print(f"Generating questions for transcript {transcript_pk}")
            
            # Validate transcript exists and belongs to user
            transcript = mongo_service.db.transcripts.find_one({'_id': ObjectId(transcript_pk)})
            if not transcript:
                return Response(
                    {'error': 'Transcript not found'},
                    status=status.HTTP_404_NOT_FOUND
                )
            
            # Get question types from request or generate all types
            question_types = request.data.get('types', qa_service.get_supported_question_types())
            if not isinstance(question_types, list):
                question_types = [question_types]
            
            created_questions = []
            
            # Generate questions for each type
            for question_type in question_types:
                if not qa_service.validate_question_type(question_type):
                    continue  # Skip invalid types
                    
                print(f"Generating {question_type} questions...")
                
                # Generate questions using QA service
                response = qa_service.generate_questions(
                    text=transcript['content'],
                    question_type=question_type
                )
                
                questions = response.get('qa_pairs', []) if isinstance(response, dict) else response
                print(f"Generated {len(questions)} {question_type} questions")
                
                # Create questions in MongoDB
                for q in questions:
                    question_data = {
                        'transcript_id': transcript_pk,
                        'video_id': transcript['video_id'],
                        'video_title': transcript.get('title', ''),
                        'question_text': q['question'],
                        'answer': q['answer'],
                        'type': question_type,
                        'options': q.get('options', []),
                        'created_at': datetime.utcnow(),
                        'attempts': 0,
                        'correct_attempts': 0
                    }
                    result = mongo_service.db.qa_pairs.insert_one(question_data)
                    question_data['_id'] = str(result.inserted_id)
                    created_questions.append(question_data)
            
            return Response(created_questions, status=status.HTTP_201_CREATED)
            
        except Exception as e:
            print(f"Error generating questions: {str(e)}")
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @action(detail=True, methods=['post'])
    def toggle_favorite(self, request, transcript_pk=None, pk=None):
        try:
            question = self.get_object()
            question.is_favorite = not question.is_favorite
            question.save()
            serializer = self.get_serializer(question)
            return Response(serializer.data)
        except Exception as e:
            return Response(
                {'error': f'Failed to toggle favorite status: {str(e)}'},
                status=status.HTTP_400_BAD_REQUEST
            )

    @action(detail=True, methods=['post'], url_path='answer')
    def submit_answer(self, request, transcript_pk=None, pk=None):
        try:
            question = self.get_object()
            submitted_answer = request.data.get('answer', '').strip()

            if not submitted_answer:
                return Response(
                    {'error': 'Answer cannot be empty'},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # Handle MongoDB question
            if isinstance(question, dict):
                correct_answer = question.get('answer', '').strip()
                is_correct = submitted_answer.lower() == correct_answer.lower()
                
                # Update MongoDB document with attempt information
                mongo_service.db.qa_pairs.update_one(
                    {'_id': ObjectId(question['_id'])},
                    {
                        '$inc': {
                            'attempts': 1,
                            'correct_attempts': 1 if is_correct else 0
                        }
                    }
                )
                
                # Get updated question data
                updated_question = mongo_service.db.qa_pairs.find_one({'_id': ObjectId(question['_id'])})
                
                return Response({
                    'is_correct': is_correct,
                    'correct_answer': correct_answer if not is_correct else None,
                    'feedback': 'Correct!' if is_correct else 'Incorrect. Try again!',
                    'attempts': updated_question.get('attempts', 1),
                    'correct_attempts': updated_question.get('correct_attempts', 1 if is_correct else 0)
                })

            # Handle Django model question
            else:
                correct_answer = question.answer.strip()
                is_correct = submitted_answer.lower() == correct_answer.lower()

                question.attempts = question.attempts + 1
                if is_correct:
                    question.correct_attempts = question.correct_attempts + 1
                question.save()

                return Response({
                    'is_correct': is_correct,
                    'correct_answer': correct_answer if not is_correct else None,
                    'feedback': 'Correct!' if is_correct else 'Incorrect. Try again!',
                    'attempts': question.attempts,
                    'correct_attempts': question.correct_attempts
                })

        except Exception as e:
            return Response(
                {'error': f'Failed to process answer: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_practice_sets(request):
    try:
        # Get all transcripts for the user from MongoDB
        transcripts = list(mongo_service.db.transcripts.find({
            'user_id': str(request.user_id)
        }))
        
        practice_sets = []
        for transcript in transcripts:
            transcript_id = str(transcript['_id'])
            # Get questions for this transcript
            questions = list(mongo_service.db.qa_pairs.find({
                'transcript_id': transcript_id
            }))
            
            if questions:
                # Group questions by type
                question_types = {}
                for q in questions:
                    q_type = q.get('type', 'novice')  # Default to novice if type not specified
                    if q_type not in question_types:
                        question_types[q_type] = []
                    question_types[q_type].append(q)
                
                # Create a practice set entry for each type
                for q_type, type_questions in question_types.items():
                    practice_sets.append({
                        'id': transcript_id,
                        'title': transcript.get('title', 'Untitled'),
                        'video_id': transcript['video_id'],
                        'type': q_type,
                        'question_count': len(type_questions)
                    })
        
        return Response(practice_sets)
    except Exception as e:
        return Response(
            {'error': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_practice_questions(request, video_id, question_type):
    try:
        # Get transcript from MongoDB
        transcript = mongo_service.db.transcripts.find_one({
            'video_id': video_id,
            'user_id': str(request.user_id)
        })
        
        if not transcript:
            return Response(
                {'error': 'Transcript not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Get questions from MongoDB
        questions = list(mongo_service.db.qa_pairs.find({
            'video_id': video_id,
            'type': question_type
        }))
        
        # Format questions for frontend
        formatted_questions = []
        for question in questions:
            formatted_question = {
                '_id': str(question['_id']),
                'question_text': question.get('question_text', ''),
                'answer': question.get('answer', ''),
                'type': question.get('type', question_type),
                'options': question.get('options', []),
                'video_id': video_id,
                'video_title': question.get('video_title', transcript.get('title', 'Untitled')),
                'attempts': question.get('attempts', 0),
                'correct_attempts': question.get('correct_attempts', 0)
            }
            formatted_questions.append(formatted_question)
        
        response_data = {
            'questions': formatted_questions,
            'transcript': transcript.get('content', ''),
            'title': transcript.get('title', 'Untitled')
        }
        
        return Response(response_data)
    except Exception as e:
        return Response(
            {'error': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def submit_answer(request, question_id):
    try:
        # Get question from MongoDB
        question = mongo_service.db.qa_pairs.find_one({
            '_id': ObjectId(question_id)
        })
        
        if not question:
            return Response(
                {'error': 'Question not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        user_answer = request.data.get('answer', '').strip()
        correct_answer = question['answer'].strip()
        is_correct = user_answer.lower() == correct_answer.lower()
        
        # Update question stats in MongoDB
        mongo_service.db.qa_pairs.update_one(
            {'_id': ObjectId(question_id)},
            {
                '$inc': {
                    'attempts': 1,
                    'correct_attempts': 1 if is_correct else 0
                }
            }
        )
        
        updated_question = mongo_service.db.qa_pairs.find_one({
            '_id': ObjectId(question_id)
        })
        
        return Response({
            'is_correct': is_correct,
            'correct_answer': correct_answer,
            'attempts': updated_question['attempts'],
            'correct_attempts': updated_question['correct_attempts']
        })
    except Exception as e:
        return Response(
            {'error': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_transcript_by_video(request, video_id):
    try:
        # Get transcript from MongoDB
        transcript = mongo_service.db.transcripts.find_one({
            'video_id': video_id,
            'user_id': str(request.user_id)
        })
        
        if not transcript:
            return Response(
                {'error': 'Transcript not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        transcript['_id'] = str(transcript['_id'])
        return Response(transcript)
    except Exception as e:
        return Response(
            {'error': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def toggle_favorite_transcript(request, transcript_id):
    try:
        # Toggle favorite in MongoDB
        result = mongo_service.toggle_transcript_favorite(
            transcript_id=transcript_id,
            user_id=str(request.user_id)
        )
        
        if not result:
            return Response(
                {'error': 'Transcript not found'},
                status=status.HTTP_404_NOT_FOUND
            )
            
        return Response({'is_favorite': result['is_favorite']})
    except Exception as e:
        return Response(
            {'error': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def toggle_favorite_question(request, question_id):
    try:
        # Toggle favorite in MongoDB
        result = mongo_service.toggle_question_favorite(
            question_id=question_id,
            user_id=str(request.user_id)
        )
        
        if not result:
            return Response(
                {'error': 'Question not found'},
                status=status.HTTP_404_NOT_FOUND
            )
            
        return Response({'is_favorite': result['is_favorite']})
    except Exception as e:
        return Response(
            {'error': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def update_question_stats(request, question_id):
    try:
        # Update question stats in MongoDB
        result = mongo_service.update_question_stats(
            question_id=question_id,
            user_id=str(request.user_id),
            is_correct=request.data.get('is_correct', False)
        )
        
        if not result:
            return Response(
                {'error': 'Question not found'},
                status=status.HTTP_404_NOT_FOUND
            )
            
        return Response({
            'attempts': result['attempts'],
            'correct_attempts': result['correct_attempts']
        })
    except Exception as e:
        return Response(
            {'error': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def query_word(request):
    try:
        word = request.data.get('word')
        if not word:
            return Response(
                {'error': 'Word is required'}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Normalize word by stripping whitespace
        word = word.strip()
        if not word:
            return Response(
                {'error': 'Word cannot be empty'}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        db = mongo_service.db
        
        # Check global dictionary first with normalized word
        global_word = db.global_words.find_one({'word': word})
        
        if global_word:
            # Word exists, increment frequency
            try:
                db.global_words.update_one(
                    {'_id': global_word['_id']},
                    {'$inc': {'frequency': 1}}
                )
                meaning_data = global_word['meaning_data']
            except Exception as e:
                logger.error(f"Error updating word frequency: {str(e)}")
                # Continue with existing meaning data even if update fails
                meaning_data = global_word['meaning_data']
        else:
            try:
                # Check for similar words (case-insensitive and ignoring spaces)
                similar_word = db.global_words.find_one({
                    'word': {'$regex': f'^{word}\\s*$', '$options': 'i'}
                })
                
                if similar_word:
                    # Use existing word instead of creating a new one
                    global_word = similar_word
                    db.global_words.update_one(
                        {'_id': global_word['_id']},
                        {'$inc': {'frequency': 1}}
                    )
                    meaning_data = global_word['meaning_data']
                else:
                    # Use qa_service to get word meaning for new word
                    meaning_data = qa_service.query_word_meaning(word)
                    
                    # Save to global dictionary
                    global_word = db.global_words.insert_one({
                        'word': word,  # Save normalized word
                        'meaning_data': meaning_data,
                        'frequency': 1,
                        'created_at': datetime.now(),
                        'last_updated': datetime.now()
                    })
                    global_word = db.global_words.find_one({'_id': global_word.inserted_id})
            except ValueError as e:
                logger.error(f"Error querying word meaning: {str(e)}")
                return Response(
                    {'error': str(e)},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )
            except Exception as e:
                logger.error(f"Unexpected error in word query: {str(e)}")
                return Response(
                    {'error': 'An unexpected error occurred while querying the word meaning'},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )

        try:
            # Add to user's list
            db.user_words.update_one(
                {
                    'user_id': str(request.user_id),
                    'word_id': global_word['_id']
                },
                {
                    '$setOnInsert': {
                        'is_mastered': False,
                        'is_favorite': False,
                        'notes': '',
                        'created_at': datetime.now()
                    }
                },
                upsert=True
            )
        except Exception as e:
            logger.error(f"Error updating user words: {str(e)}")
            # Continue even if user words update fails
            pass

        return Response({
            'word': word,
            'data': meaning_data,
            'frequency': global_word.get('frequency', 1)
        })

    except Exception as e:
        logger.error(f"Error in query_word: {str(e)}")
        return Response(
            {'error': 'An unexpected error occurred while processing your request'}, 
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def toggle_word_favorite(request, word_id):
    try:
        db = mongo_service.db
        
        # Find the user's word entry
        user_word = db.user_words.find_one({
            'user_id': str(request.user_id),
            'word_id': ObjectId(word_id)
        })
        
        if not user_word:
            return Response(
                {'error': 'Word not found in user\'s list'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Toggle the is_favorite status
        new_status = not user_word.get('is_favorite', False)
        db.user_words.update_one(
            {
                'user_id': str(request.user_id),
                'word_id': ObjectId(word_id)
            },
            {
                '$set': {
                    'is_favorite': new_status,
                    'updated_at': datetime.now()
                }
            }
        )
        
        return Response({
            'word_id': str(word_id),
            'is_favorite': new_status
        })
        
    except Exception as e:
        logger.error(f"Error in toggle_word_favorite: {str(e)}")
        return Response(
            {'error': 'Failed to toggle favorite status'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_user_words(request):
    try:
        db = mongo_service.db
        
        # Get filter parameters
        favorites_only = request.query_params.get('favorites', '').lower() == 'true'
        
        # Base match condition
        match_condition = {
                    'user_id': str(request.user_id)
                }
        
        # Add favorites filter if requested
        if favorites_only:
            match_condition['is_favorite'] = True
        
        current_time = datetime.now()
        user_words = list(db.user_words.aggregate([
            {
                '$match': match_condition
            },
            {
                '$lookup': {
                    'from': 'global_words',
                    'localField': 'word_id',
                    'foreignField': '_id',
                    'as': 'word_details'
                }
            },
            {
                '$unwind': '$word_details'
            },
            {
                '$project': {
                    '_id': { '$toString': '$_id' },
                    'word_id': { '$toString': '$word_id' },
                    'word': '$word_details.word',
                    'meaning': {
                        'meaning': '$word_details.meaning_data.meaning',
                        'example': {
                            'hindi': '$word_details.meaning_data.example.hindi',
                            'english': '$word_details.meaning_data.example.english'
                        }
                    },
                    'frequency': { '$ifNull': ['$word_details.frequency', 1] },
                    'is_mastered': { '$ifNull': ['$is_mastered', False] },
                    'is_favorite': { '$ifNull': ['$is_favorite', False] },
                    'notes': { '$ifNull': ['$notes', ''] },
                    'created_at': { '$ifNull': ['$created_at', current_time] }
                }
            },
            {
                '$sort': {
                    'created_at': -1
                }
            }
        ]))

        return Response({
            'words': user_words,
            'count': len(user_words)
        })
    except Exception as e:
        logger.error(f"Error in get_user_words: {str(e)}")
        return Response(
            {'error': 'Failed to fetch user words. Please try again.'}, 
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def update_word_notes(request, word_id):
    try:
        db = mongo_service.db
        notes = request.data.get('notes', '').strip()
        
        # Find the user's word entry
        user_word = db.user_words.find_one({
            'user_id': str(request.user_id),
            'word_id': ObjectId(word_id)
        })
        
        if not user_word:
            return Response(
                {'error': 'Word not found in user\'s list'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Update the notes
        db.user_words.update_one(
            {
                'user_id': str(request.user_id),
                'word_id': ObjectId(word_id)
            },
            {
                '$set': {
                    'notes': notes,
                    'updated_at': datetime.now()
                }
            }
        )
        
        return Response({
            'word_id': str(word_id),
            'notes': notes
        })
        
    except Exception as e:
        logger.error(f"Error in update_word_notes: {str(e)}")
        return Response(
            {'error': 'Failed to update notes'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

@api_view(['GET'])
@permission_classes([AllowAny])
def get_trending_words(request):
    try:
        db = mongo_service.db
        # Get top 3 words by frequency
        trending_words = list(db.global_words.find(
            {},
            {'word': 1, 'meaning_data': 1, 'frequency': 1}
        ).sort('frequency', -1).limit(3))

        # Format the response
        formatted_words = [{
            'word': word['word'],
            'meaning': word['meaning_data']['meaning'],
            'frequency': word.get('frequency', 1)
        } for word in trending_words]

        return Response(formatted_words)
    except Exception as e:
        logger.error(f"Error fetching trending words: {str(e)}")
        return Response(
            {'error': 'Failed to fetch trending words'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )
