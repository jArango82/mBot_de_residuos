"""Índices de cámara en el orden real del backend OpenCV AVFoundation."""
from functools import cmp_to_key


def opencv_devices(av=None):
    if av is None:
        import AVFoundation as av
    # OpenCV concatena vídeo y muxed, y ordena usando NSString.compare:.
    # No coincide con el orden de devicesWithMediaType_ por sí solo.
    devices = list(av.AVCaptureDevice.devicesWithMediaType_(av.AVMediaTypeVideo))
    devices += list(av.AVCaptureDevice.devicesWithMediaType_(av.AVMediaTypeMuxed))
    def compare(a, b):
        from Foundation import NSString
        left = NSString.stringWithString_(str(a.uniqueID()))
        return int(left.compare_(str(b.uniqueID())))
    return sorted(devices, key=cmp_to_key(compare))


def select_external(requested=None, devices=None):
    devices = opencv_devices() if devices is None else devices
    if requested is None:
        matches = [i for i, d in enumerate(devices)
                   if 'Microsoft LifeCam' in str(d.localizedName())]
        if len(matches) != 1:
            raise RuntimeError('Conecta una unica Microsoft LifeCam externa. No se abrira la camara del Mac.')
        index = matches[0]
    else:
        index = requested
    if not 0 <= index < len(devices):
        raise RuntimeError('Indice de camara no disponible.')
    device = devices[index]
    if 'Microsoft LifeCam' not in str(device.localizedName()):
        raise RuntimeError('Ese indice no corresponde a la LifeCam externa; se cancela la captura.')
    return index, str(device.localizedName()), str(device.uniqueID())
