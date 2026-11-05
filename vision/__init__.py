"""
Paquete ``vision``: todo el procesamiento de imagen y video con OpenCV.

Este paquete NO depende de Django. Así se puede probar por separado y
reutilizar en otro proyecto (por ejemplo, un script de escritorio).

Flujo de cada fotograma (ver ``camara.GestorCamara``)::

    cámara (cv2.VideoCapture)
        -> espejo horizontal (cv2.flip)
        -> escala de grises (cv2.cvtColor)
        -> detección de rostros (Haar Cascade, cv2.CascadeClassifier)
        -> clasificación de la expresión (modelo FER+ ONNX con cv2.dnn)
        -> suavizado temporal de las probabilidades
        -> decisión (sensibilidad.py): línea base de la cara neutra, cambio
           respecto a ella y ventana 3 de 5 (solo el modelo FER+ decide)
        -> dibujo de resultados sobre el video (cv2.rectangle, cv2.putText, emoji)
        -> codificación JPEG (cv2.imencode) para el navegador
"""
