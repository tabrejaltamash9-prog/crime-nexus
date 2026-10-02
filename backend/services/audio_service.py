import asyncio
import logging
from pathlib import Path
import os

# STUB mode flag to unblock hackathon development without requiring massive GPU downloads
USE_STUB = True

try:
    import whisper
    # from pyannote.audio import Pipeline
except ImportError:
    logging.warning("Audio dependencies (whisper/pyannote) missing. Falling back to STUB mode.")
    USE_STUB = True

logger = logging.getLogger(__name__)

async def extract_transcript_from_audio(file_path: Path) -> str:
    """
    Extract transcript with speaker diarization from audio file.
    Runs whisper and pyannote in parallel/sequence.
    """
    if USE_STUB:
        logger.info(f"STUB: Extracting transcript from {file_path.name}")
        await asyncio.sleep(3)  # Simulate processing time
        return (
            "[00:00:00 - 00:00:05] SPEAKER_01: Did you transfer the funds to the offshore account?\n"
            "[00:00:05 - 00:00:10] SPEAKER_02: Yes, Rahul confirmed receipt yesterday."
        )
    
    transcript = ""
    try:
        # Run actual extraction in a thread pool
        transcript = await asyncio.to_thread(_run_audio_pipeline, file_path)
    except Exception as e:
        logger.error(f"Audio processing failed for {file_path.name}: {e}")
        transcript = f"[AUDIO FAILED]: {str(e)}"
    
    return transcript

def _run_audio_pipeline(file_path: Path) -> str:
    """
    Actual implementation for whisper + pyannote diarization.
    """
    # 1. Load Whisper model
    model = whisper.load_model("base")
    
    # 2. Transcribe audio
    logger.info("Running Whisper transcription...")
    result = model.transcribe(str(file_path))
    
    # 3. Speaker Diarization (Pyannote)
    # Note: Requires HUGGINGFACE_TOKEN in env and accepted terms on HF
    # pipeline = Pipeline.from_pretrained(
    #     "pyannote/speaker-diarization-3.1",
    #     use_auth_token=os.environ.get("HUGGINGFACE_TOKEN")
    # )
    # diarization = pipeline(str(file_path))
    
    # In a full implementation, we would align Whisper timestamps with Pyannote segments
    # For now, if not in stub mode, we just return the Whisper transcript
    
    formatted_text = ""
    for segment in result["segments"]:
        start = segment["start"]
        end = segment["end"]
        text = segment["text"]
        # Simplified formatting without speaker labels (since Pyannote setup is complex)
        formatted_text += f"[{start:.2f}s - {end:.2f}s] {text.strip()}\n"
        
    return formatted_text
