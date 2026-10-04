"""stdio MCP adapter. Audio never leaves the local machine."""
import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import native_client
from mcp.server.fastmcp import FastMCP

mcp=FastMCP('Signal Radar Transcription')

@mcp.tool()
def transcribe_audio(file_path:str, language:str='') -> dict:
    """Submit a local audio/video file; returns an asynchronous job ID. language: zh, en, or empty."""
    path=Path(file_path).expanduser().resolve()
    if not path.is_file() or path.stat().st_size>512*1024*1024:raise ValueError('需要不超过512 MB的媒体文件')
    return native_client.upload_file(path,language)

@mcp.tool()
def get_transcription(job_id:str) -> dict:
    """Read job status and the completed transcript with segment timestamps."""
    if not job_id.isalnum():raise ValueError('无效任务ID')
    return native_client.call('/v1/transcription-jobs/'+job_id)

@mcp.tool()
def cancel_transcription(job_id:str) -> dict:
    """Cancel a queued or running transcription job."""
    if not job_id.isalnum():raise ValueError('无效任务ID')
    return native_client.call('/v1/transcription-jobs/'+job_id+'/cancel',{})

if __name__=='__main__':mcp.run()
