try:
    import tensorflow as tf
    print(f"✅ TensorFlow version: {tf.__version__}")
    print("TensorFlow is successfully installed!")
except ImportError as e:
    print(f"❌ TensorFlow not installed: {e}")
except Exception as e:
    print(f"❌ Error importing TensorFlow: {e}")