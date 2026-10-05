#!/usr/bin/env python3
"""Descarga modelos oficiales y prepara las categorías; no abre cámara ni robot."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess

BASE = Path(__file__).resolve().parent
MODELS = BASE / 'models'
CLIP_SHA = '40d365715913c9da98579312b702a82c18be219cc2a73407c4526f58eba950af'
DINO_REV = 'a2bb814dd30d776dcf7e30523b00659f4f141c71'

def download(url, target, digest=None):
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.is_file() and target.stat().st_size:
        if digest is None or hashlib.sha256(target.read_bytes()).hexdigest() == digest:
            return
    temporary = target.with_name(target.name + '.partial')
    subprocess.run(['curl', '--fail', '--location', '--retry', '3', url, '-o', str(temporary)], check=True)
    if digest and hashlib.sha256(temporary.read_bytes()).hexdigest() != digest:
        raise RuntimeError('No coincide la verificación de ' + target.name)
    temporary.replace(target)

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--comprobar', action='store_true', help='Solo comprobar si están los archivos necesarios')
    args = parser.parse_args()
    required = ['yolo11n.pt', 'residuos-world-small.pt', 'clip/ViT-B-32.pt',
                'grounding-dino-tiny/model.safetensors']
    if args.comprobar:
        missing = [name for name in required if not (MODELS/name).is_file()]
        if missing:
            raise SystemExit('Faltan: ' + ', '.join(missing))
        print('Los archivos de modelos necesarios están presentes.')
        return
    os.environ.setdefault('YOLO_CONFIG_DIR', str(BASE.parent/'work/yolo-config'))
    os.environ.setdefault('MPLCONFIGDIR', str(BASE.parent/'work/matplotlib'))
    download(f'https://openaipublic.azureedge.net/clip/models/{CLIP_SHA}/ViT-B-32.pt',
             MODELS/'clip/ViT-B-32.pt', CLIP_SHA)
    for name in ['yolo11n.pt', 'yolov8s-worldv2.pt']:
        download('https://github.com/ultralytics/assets/releases/download/v8.4.0/'+name, MODELS/name)
    for name in ['config.json','model.safetensors','preprocessor_config.json','special_tokens_map.json',
                 'tokenizer.json','tokenizer_config.json','vocab.txt','added_tokens.json']:
        download(f'https://huggingface.co/IDEA-Research/grounding-dino-tiny/resolve/{DINO_REV}/{name}',
                 MODELS/'grounding-dino-tiny'/name)
    from ultralytics import YOLOWorld, settings
    import clip
    settings.update({'sync': False, 'weights_dir': str(MODELS)})
    categories = json.loads((MODELS/'residuos-categorias.json').read_text())
    model = YOLOWorld(str(MODELS/'yolov8s-worldv2.pt'))
    # Cargar CLIP por ruta evita descargas implícitas fuera del proyecto.
    import torch
    encoder, _ = clip.load(str(MODELS/'clip/ViT-B-32.pt'), device='cpu')
    with torch.inference_mode():
        features = encoder.encode_text(clip.tokenize([prompt for prompt, _ in categories]))
        features = features / features.norm(dim=-1, keepdim=True)
    model.model.txt_feats = features.reshape(1, len(categories), -1)
    model.model.model[-1].nc = len(categories)
    model.model.names = {i:label for i,(_,label) in enumerate(categories)}
    model.model.clip_model = None
    model.save(str(MODELS/'residuos-world-small.pt'))
    print('Modelos preparados. Abre Detectar_Residuos.command.')

if __name__ == '__main__':
    main()
