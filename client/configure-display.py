#!/usr/bin/env python3
"""Apply the spectator's persistent 1080p/max-quality profile before every launch."""
import pathlib
import re
import sys

PROFILE = {
    # Stock zoom range; spectator angles stay where the viewer puts them.
    'cameraDistanceMax':'15', 'cameraDistanceMaxFactor':'1',
    'cameraSmoothStyle':'0', 'cameraSmoothTrackingStyle':'0',
    'cameraTerrainTilt':'0', 'cameraBobbing':'0', 'cameraPivot':'0',
    'gxResolution':'1920x1080', 'gxWindow':'1', 'windowResizeLock':'1',
    'useUiScale':'1', 'uiScale':'1.0', 'gxMultisample':'8',
    'textureFilteringMode':'5', 'baseMip':'0', 'shadowLevel':'0',
    'componentTextureLevel':'9', 'environmentDetail':'1.5',
    'groundEffectDensity':'256', 'groundEffectDist':'140', 'farclip':'1277',
    'particleDensity':'1.0', 'spellEffectLevel':'9', 'weatherDensity':'3',
    'projectedTextures':'1', 'specular':'1', 'ffx':'1', 'ffxGlow':'1',
    'ffxDeath':'1', 'pixelShaders':'1', 'gxVSync':'1',
}

def configure(path):
    text = path.read_text() if path.exists() else ''
    match = re.search(r'^\[cvars\]\s*$', text, re.M)
    if not match:
        text += '\n[cvars]\n'
        match = re.search(r'^\[cvars\]\s*$', text, re.M)
    start = match.end()
    following = re.search(r'^\[', text[start:], re.M)
    end = start + following.start() if following else len(text)
    section = text[start:end]
    for key, value in PROFILE.items():
        line = f'{key} = "{value}"'
        pattern = rf'^{re.escape(key)}\s*=.*$'
        if re.search(pattern, section, re.M):
            section = re.sub(pattern, line, section, flags=re.M)
        else:
            section = section.rstrip() + '\n' + line + '\n'
    path.write_text(text[:start] + '\n' + section.lstrip('\n') + text[end:])

if __name__ == '__main__':
    configure(pathlib.Path(sys.argv[1]))
