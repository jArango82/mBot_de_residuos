#!/usr/bin/env python3
"""Entrena un detector YOLO con las fotos etiquetadas de work/dataset y lo evalúa con una sesión reservada.

Etiquetas: work/dataset/etiquetas/<sesión>.json con {"classes": [...], "labels": {"0001.jpg": [{"cls": 0,
"box": [x1, y1, x2, y2]}, ...]}} en píxeles de la imagen original. Las fotos están en
work/dataset/imagenes/<sesión>/. La sesión indicada con --prueba no se usa para aprender.
"""
import argparse
import json
import os
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]
DATASET = ROOT / 'work/dataset'
os.environ.setdefault('YOLO_CONFIG_DIR', str(ROOT / 'work/yolo-config'))
OUTPUT = ROOT / 'outputs/models/residuos-propio.pt'


def sessions():
    """Sesiones con etiquetas revisadas; los .dino.json son preetiquetas sin revisar."""
    found = {}
    for path in sorted((DATASET / 'etiquetas').glob('*.json')):
        if not path.name.endswith('.dino.json'):
            found[path.stem] = json.loads(path.read_text())
    if not found:
        raise RuntimeError('No hay etiquetas en work/dataset/etiquetas.')
    classes = {tuple(d['classes']) for d in found.values()}
    if len(classes) != 1:
        raise RuntimeError('Las sesiones tienen listas de clases distintas.')
    return found, list(classes.pop())


def yolo_line(obj, width, height):
    x1, y1, x2, y2 = obj['box']
    x1, x2 = max(0., min(x1, x2)), min(float(width), max(x1, x2))
    y1, y2 = max(0., min(y1, y2)), min(float(height), max(y1, y2))
    if x2 - x1 < 2 or y2 - y1 < 2:
        return None
    return (f"{obj['cls']} {(x1 + x2) / 2 / width:.6f} {(y1 + y2) / 2 / height:.6f} "
            f"{(x2 - x1) / width:.6f} {(y2 - y1) / height:.6f}")


def build(found, classes, test, folder):
    """Carpeta en formato YOLO: enlaces a las fotos y un .txt por foto (vacío si no hay residuos)."""
    import cv2
    if folder.exists():
        shutil.rmtree(folder)
    counts = {'train': 0, 'val': 0}
    for session, data in found.items():
        split = 'val' if session == test else 'train'
        (folder / 'images' / split).mkdir(parents=True, exist_ok=True)
        (folder / 'labels' / split).mkdir(parents=True, exist_ok=True)
        for name, objs in data['labels'].items():
            image = DATASET / 'imagenes' / session / name
            if not image.is_file():
                continue
            height, width = cv2.imread(str(image)).shape[:2]
            stem = f'{session}__{Path(name).stem}'
            (folder / 'images' / split / f'{stem}.jpg').symlink_to(image)
            lines = [line for line in (yolo_line(o, width, height) for o in objs) if line]
            (folder / 'labels' / split / f'{stem}.txt').write_text('\n'.join(lines))
            counts[split] += 1
    if not counts['val']:
        raise RuntimeError(f'La sesion de prueba "{test}" no tiene fotos etiquetadas.')
    yaml = folder / 'data.yaml'
    yaml.write_text(f'path: {folder}\ntrain: images/train\nval: images/val\n'
                    f'names: {json.dumps(dict(enumerate(classes)), ensure_ascii=False)}\n')
    return yaml, counts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prueba', required=True, help='Sesion reservada para evaluar (no se aprende de ella)')
    parser.add_argument('--epocas', type=int, default=80)
    parser.add_argument('--tam', type=int, default=960, help='Lado de imagen para entrenar')
    parser.add_argument('--base', default=str(ROOT / 'outputs/models/yolo11n.pt'), help='Modelo YOLO de partida')
    args = parser.parse_args()
    import torch
    from ultralytics import YOLO, settings
    settings.update({'sync': False})
    found, classes = sessions()
    folder = DATASET / 'yolo'
    yaml, counts = build(found, classes, args.prueba, folder)
    print(f'Clases: {classes} | fotos para aprender: {counts["train"]} | fotos de prueba: {counts["val"]}', flush=True)
    device = 'mps' if torch.backends.mps.is_available() else 'cpu'
    # Vista cenital: los residuos pueden aparecer en cualquier giro, así que se gira y voltea al aprender.
    YOLO(args.base).train(data=str(yaml), epochs=args.epocas, imgsz=args.tam, batch=8, device=device, workers=0,
                          degrees=180, flipud=.5, project=str(ROOT / 'work/entrenamientos'), name='residuos-propio',
                          exist_ok=True, plots=False, verbose=False, seed=0)
    # Se usa el modelo de la última época, no el que mejor puntúa en la prueba: así la prueba sigue siendo honesta.
    last = ROOT / 'work/entrenamientos/residuos-propio/weights/last.pt'
    shutil.copy(last, OUTPUT)
    metrics = YOLO(str(OUTPUT)).val(data=str(yaml), imgsz=args.tam, device=device, workers=0, plots=False, verbose=False)
    report = {'clases': classes, 'fotos_aprender': counts['train'], 'fotos_prueba': counts['val'], 'sesion_prueba': args.prueba,
              'mAP50': round(float(metrics.box.map50), 3),
              'mAP50_por_clase': {classes[int(c)]: round(float(v), 3) for c, v in zip(metrics.box.ap_class_index, metrics.box.ap50)}}
    (ROOT / 'work/entrenamientos/residuos-propio/resultado.json').write_text(json.dumps(report, indent=2, ensure_ascii=False))
    print('Modelo guardado en', OUTPUT, '\n' + json.dumps(report, indent=2, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
