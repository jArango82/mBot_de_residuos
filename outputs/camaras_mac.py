"""Índices de cámara en el orden real del backend OpenCV AVFoundation."""
import argparse
from functools import cmp_to_key

# Cámaras externas que se eligen solas cuando hay una única conectada.
# El Samsung puede aparecer con su propio nombre (modo Cámara web USB) o como Camo.
PROFILES = [
    ('LifeCam', ('microsoft lifecam',)),
    ('Samsung', ('samsung', 'galaxy', 'sm-s928', 'android')),
    ('Camo', ('camo',)),
]
# Marca de agua fija de Camo gratuito (medida a 1280x720: 88,7-96 % del ancho, 81,1-94,7 % del
# alto), con un pequeño margen. Las detecciones que caen sobre ella no son residuos.
WATERMARKS = {'Camo': (.87, .79, .975, .965)}
BUILTIN_TYPE = 'AVCaptureDeviceTypeBuiltInWideAngleCamera'
BUILTIN_TRANSPORT = int.from_bytes(b'bltn', 'big')
BUILTIN_NAMES = ('macbook', 'facetime', 'imac')


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


def profile(device):
    name = str(device.localizedName()).lower()
    return next((label for label, words in PROFILES if any(w in name for w in words)), None)


def is_builtin(device):
    """La cámara del Mac nunca se usa, ni siquiera pidiéndola por índice o nombre."""
    kind = getattr(device, 'deviceType', None)
    transport = getattr(device, 'transportType', None)
    name = str(device.localizedName()).lower()
    return ((kind is not None and str(kind()) == BUILTIN_TYPE) or
            (transport is not None and transport() == BUILTIN_TRANSPORT) or
            any(word in name for word in BUILTIN_NAMES))


def native_size(device):
    """Tamaño del formato activo; permite pedir la misma proporción y no deformar la imagen."""
    try:
        from CoreMedia import CMVideoFormatDescriptionGetDimensions
        size = CMVideoFormatDescriptionGetDimensions(device.activeFormat().formatDescription())
        return (int(size.width), int(size.height)) if size.width > 0 and size.height > 0 else None
    except Exception:
        return None


def describe(devices=None):
    devices = opencv_devices() if devices is None else devices
    rows = []
    for i, d in enumerate(devices):
        kind = 'integrada (no se usa)' if is_builtin(d) else (profile(d) or 'externa sin perfil')
        rows.append(f'{i}: {d.localizedName()} | {kind}')
    return rows


def _seen(devices):
    return '; '.join(describe(devices)) or 'ninguna'


def select_external(requested=None, devices=None):
    """requested: None (automático), índice de OpenCV o parte del nombre."""
    devices = opencv_devices() if devices is None else devices
    external = [i for i, d in enumerate(devices) if not is_builtin(d)]
    if requested is None:
        matches = [i for i in external if profile(devices[i])]
        if not matches:
            raise RuntimeError('No hay una camara externa reconocida (LifeCam, Samsung o Camo). '
                               'Vistas: ' + _seen(devices) + '. Usa --camara "nombre" para elegir otra externa. '
                               'No se abrira la camara del Mac.')
        if len(matches) > 1:
            raise RuntimeError('Hay varias camaras externas: ' + _seen(devices) +
                               '. Elige una con --camara "nombre" o su numero.')
        index = matches[0]
    elif isinstance(requested, str):
        text = requested.strip().lower()
        # «samsung» también elige un «Galaxy S24 Ultra» o «Android Webcam» por su perfil.
        matches = [i for i in external if text and (text in str(devices[i].localizedName()).lower() or
                                                    text == (profile(devices[i]) or '').lower())]
        if len(matches) != 1:
            raise RuntimeError(('Varias' if matches else 'Ninguna') + f' camara externa coincide con "{requested}". '
                               'Vistas: ' + _seen(devices) + '. No se abrira la camara del Mac.')
        index = matches[0]
    else:
        index = requested
        if not 0 <= index < len(devices):
            raise RuntimeError('Indice de camara no disponible.')
    device = devices[index]
    if is_builtin(device):
        raise RuntimeError('Ese indice corresponde a la camara del Mac; se cancela la captura.')
    return index, str(device.localizedName()), str(device.uniqueID())


def camera_arg(text):
    """Para argparse: un número es índice; cualquier otro texto, parte del nombre."""
    return int(text) if text.strip().isdigit() else text


def size_arg(text):
    """Para argparse: ANCHOxALTO, por ejemplo 1280x720."""
    try:
        width, height = (int(v) for v in text.lower().split('x'))
    except ValueError:
        raise argparse.ArgumentTypeError('usa ANCHOxALTO, por ejemplo 1280x720') from None
    if not (160 <= width <= 3840 and 120 <= height <= 3840):
        raise argparse.ArgumentTypeError('resolucion fuera de rango')
    return width, height
