"""Curated presenters and voices; selections are private to each connection."""
from copy import deepcopy

AVATARS = [
    {'id': 'hr-warm', 'name': '知夏', 'description': '亲和女面试官', 'image': '/avatars/hr-warm.png'},
    {'id': 'hr-calm', 'name': '明远', 'description': '沉稳男面试官', 'image': '/avatars/hr-calm.png'},
    {'id': 'hr-senior', 'name': '若宁', 'description': '资深女面试官', 'image': '/avatars/hr-senior.png'},
]
VOICES = [
    {'id': 'minimax-kobe-clone', 'name': '科比 · 复刻音色'},
    {'id': 'zh-CN-XiaoxiaoNeural', 'name': '晓晓 · 女声'},
    {'id': 'zh-CN-XiaoyiNeural', 'name': '晓伊 · 女声'},
    {'id': 'zh-CN-YunxiNeural', 'name': '云希 · 男声'},
    {'id': 'zh-CN-YunjianNeural', 'name': '云健 · 男声'},
]
DEFAULT_AVATAR = AVATARS[0]['id']
DEFAULT_VOICE = 'zh-CN-XiaoxiaoNeural'


def validate_voice(voice_id):
    if voice_id not in [voice['id'] for voice in VOICES]:
        raise ValueError('请选择列表中的音色。')
    return voice_id


def prepare_presentation(params, base_config, loader):
    avatar_id = params.get('avatar_id', DEFAULT_AVATAR)
    if avatar_id not in [avatar['id'] for avatar in AVATARS]:
        raise ValueError('请选择列表中的面试官。')
    voice_id = validate_voice(params.get('voice_id', DEFAULT_VOICE))
    config = deepcopy(base_config)
    config.model.avatar_id = avatar_id
    config.tts.ref_file = voice_id
    try:
        frames = loader(avatar_id)
    except FileNotFoundError:
        raise ValueError('该面试官素材尚未准备完成，请运行 scripts/prepare-presenters.py。') from None
    return config, frames
