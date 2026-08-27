from pathlib import Path
import sys

import numpy as np
import onnxruntime as ort
from PIL import Image, ImageFilter


def multiple_of_14(value: float) -> int:
    return max(14, round(value / 14) * 14)


def main() -> None:
    if len(sys.argv) != 4:
        raise SystemExit("usage: generate_depth.py MODEL INPUT OUTPUT")

    model_path, input_path, output_path = map(Path, sys.argv[1:])
    source = Image.open(input_path).convert("RGB")
    target_height = 518
    target_width = multiple_of_14(target_height * source.width / source.height)
    resized = source.resize((target_width, target_height), Image.Resampling.LANCZOS)

    pixels = np.asarray(resized, dtype=np.float32) / 255.0
    mean = np.asarray([0.485, 0.456, 0.406], dtype=np.float32)
    std = np.asarray([0.229, 0.224, 0.225], dtype=np.float32)
    tensor = ((pixels - mean) / std).transpose(2, 0, 1)[None]

    session = ort.InferenceSession(str(model_path), providers=["CPUExecutionProvider"])
    depth = session.run(None, {"pixel_values": tensor})[0][0]
    low, high = np.percentile(depth, [2, 98])
    depth = np.clip((depth - low) / max(high - low, 1e-6), 0, 1)
    depth_image = Image.fromarray(np.uint8(depth * 255), mode="L")
    depth_image = depth_image.resize(source.size, Image.Resampling.BICUBIC).filter(ImageFilter.GaussianBlur(1.1))
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    depth_image.save(output_path, optimize=True)
    print(f"saved {output_path} ({source.width}x{source.height}, inference {target_width}x{target_height})")


if __name__ == "__main__":
    main()
