# We no longer need Django models as we're using MongoDB
# This file can be empty or contain documentation about our MongoDB schema

"""
MongoDB Schema Documentation

Collections:

1. transcripts
{
    '_id': ObjectId,
    'user_id': str,
    'video_id': str,
    'title': str,
    'content': str,
    'language': str,
    'created_at': datetime,
    'updated_at': datetime,
    'is_favorite': bool
}

2. qa_pairs
{
    '_id': ObjectId,
    'transcript_id': str,
    'video_id': str,
    'video_title': str,
    'question_text': str,
    'answer': str,
    'type': str,
    'options': list[str],
    'created_at': datetime,
    'attempts': int,
    'correct_attempts': int
}

3. user_progress
{
    '_id': ObjectId,
    'user_id': str,
    'video_id': str,
    'type': str,
    'answers': dict,
    'updated_at': datetime
}


4. global_words
{
    '_id': ObjectId,
    'word': str,          # The Hindi word
    'meaning': str,       # Explanation from Deepseek
    'frequency': int,     # How many times users have queried this
    'created_at': datetime,
    'last_updated': datetime
}

5. user_words
{
    '_id': ObjectId,
    'user_id': str,      # Reference to user
    'word_id': ObjectId, # Reference to global_words
    'is_mastered': bool,
    'notes': str,        # Optional personal notes
    'created_at': datetime
}
"""