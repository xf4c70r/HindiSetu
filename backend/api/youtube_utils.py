from youtube_transcript_api import YouTubeTranscriptApi
import re
import logging
import time
from random import uniform

logger = logging.getLogger(__name__)

def extract_video_id(url):
    """Extract video ID from YouTube URL."""
    logger.info(f"Attempting to extract video ID from URL: {url}")
    
    # Regular expressions for different YouTube URL formats
    patterns = [
        r'(?:v=|\/)([0-9A-Za-z_-]{11}).*',  # Standard and short URLs
        r'(?:embed\/)([0-9A-Za-z_-]{11})',   # Embed URLs
        r'^([0-9A-Za-z_-]{11})$'             # Direct video ID
    ]
    
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            video_id = match.group(1)
            logger.info(f"Successfully extracted video ID: {video_id}")
            return video_id
    
    logger.error(f"Failed to extract video ID from URL: {url}")
    return None

def get_transcript_with_retry(video_id, max_retries=3, initial_delay=1):
    """Get transcript with retry logic."""
    delay = initial_delay
    last_exception = None
    
    for attempt in range(max_retries):
        try:
            logger.info(f"Attempting to fetch transcripts for video ID: {video_id}")
            transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
            available_languages = [t.language_code for t in transcript_list]
            logger.info(f"Available languages: {available_languages}")
            
            # Try to get Hindi transcript
            try:
                transcript = transcript_list.find_transcript(['hi'])
                language = 'hi'
                logger.info("Found Hindi transcript")
            except Exception as e:
                logger.warning(f"Hindi transcript not found: {str(e)}")
                # If Hindi not available, get any available transcript
                transcript = transcript_list.find_transcript(['en'])
                language = 'en'
                logger.info("Found English transcript")
            
            transcript_data = transcript.fetch()
            logger.info(f"Successfully fetched {language} transcript with {len(transcript_data)} entries")
            return transcript_data, language
            
        except Exception as e:
            last_exception = e
            if "Too Many Requests" in str(e):
                wait_time = delay * (1 + uniform(0, 0.1))  # Add some randomness
                logger.warning(f"Rate limited by YouTube. Waiting {wait_time:.2f} seconds before retry {attempt + 1}/{max_retries}")
                time.sleep(wait_time)
                delay *= 2  # Exponential backoff
            else:
                # If it's not a rate limit error, don't retry
                raise
    
    # If we've exhausted all retries
    raise ValueError(f"Could not fetch transcript after {max_retries} attempts: {str(last_exception)}")

def get_transcript(video_id):
    """Get transcript from YouTube video."""
    try:
        logger.info(f"Attempting to fetch transcripts for video ID: {video_id}")
        return get_transcript_with_retry(video_id)
    except Exception as e:
        logger.error(f"Error in get_transcript: {str(e)}")
        import traceback
        logger.error(f"Full traceback: {traceback.format_exc()}")
        raise ValueError(f"Could not fetch transcript: {str(e)}")

def format_transcript(transcript_data):
    """Format transcript data into readable text."""
    try:
        logger.info(f"Formatting transcript with {len(transcript_data)} entries")
        
        # Clean and join the text entries
        formatted_lines = []
        for entry in transcript_data:
            text = entry['text'].strip()
            
            # Skip empty lines
            if not text:
                continue
                
            # Skip music notations and other non-text content
            skip_patterns = ['[संगीत]', '[Music]', '[Applause]', '[Laughter]', '[Background]']
            if any(pattern in text for pattern in skip_patterns):
                continue
            
            # Clean up common formatting issues
            text = re.sub(r'\s+', ' ', text)  # Normalize whitespace
            text = text.replace(' ।', '।')  # Fix spacing around punctuation
            text = text.replace(' ?', '?')
            text = text.replace(' !', '!')
            text = text.replace('..', '…')  # Convert multiple dots to ellipsis
            
            # Only add non-empty lines after cleaning
            if text.strip():
                formatted_lines.append(text)
        
        # Join lines with proper spacing
        formatted_text = ' '.join(formatted_lines)
        
        # Final cleanup
        formatted_text = formatted_text.strip()
        formatted_text = re.sub(r'\s+', ' ', formatted_text)  # Final whitespace normalization
        
        # Logging
        logger.info(f"Formatted transcript length: {len(formatted_text)} characters")
        logger.debug(f"Formatted transcript preview: {formatted_text[:200]}")
        
        return formatted_text
        
    except Exception as e:
        logger.error(f"Error formatting transcript: {str(e)}")
        logger.error(f"Transcript data preview: {str(transcript_data[:2])}")
        raise ValueError(f"Failed to format transcript: {str(e)}") 