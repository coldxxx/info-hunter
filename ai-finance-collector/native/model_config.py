import os
from pathlib import Path

MODEL = 'mlx-community/whisper-large-v3-turbo'


def model_path():
    """Reuse the model managed by LM Studio without downloading another copy."""
    default = Path.home() / '.lmstudio' / 'models' / MODEL
    folder = Path(os.environ.get('RADAR_WHISPER_MODEL_DIR', str(default))).expanduser().resolve()
    if not (folder / 'config.json').is_file() or not any(
        (folder / name).is_file() and (folder / name).stat().st_size > 0
        for name in ('weights.safetensors', 'weights.npz')
    ):
        raise ValueError('Whisper 模型未就绪，请在 LM Studio 完成 mlx-community/whisper-large-v3-turbo 的下载；模型放在自定义目录时请设置 RADAR_WHISPER_MODEL_DIR')
    return folder
