import argparse
import sys
from .pollo_img2vid import create_video, GENERATORS


def main():
    parser = argparse.ArgumentParser(
        description="Pollo Video Generator CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=f"Available models: {', '.join(GENERATORS)}",
    )
    parser.add_argument("-m", "--model", default=None,
                        help="Model to use (default: pollodance20)")
    parser.add_argument("-p", "--project", default=None,
                        help="Project folder name under projects/")
    parser.add_argument("-r", "--ratio", dest="aspect_ratio", default=None,
                        help="Aspect ratio, e.g. 9:16, 16:9, 4:3")
    parser.add_argument("-l", "--length", type=int, default=None,
                        help="Video length in seconds")
    parser.add_argument("--resolution", default=None,
                        help="Output resolution e.g. 480p, 720p")
    parser.add_argument("--audio", dest="generate_audio", action="store_true", default=False,
                        help="Enable audio generation")

    args = parser.parse_args()

    try:
        create_video(
            model=args.model,
            project=args.project,
            aspect_ratio=args.aspect_ratio,
            length=args.length,
            resolution=args.resolution,
            generate_audio=args.generate_audio,
        )
    except ValueError as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
