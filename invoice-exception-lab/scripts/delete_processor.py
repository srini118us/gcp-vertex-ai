"""Teardown: delete the Document AI processor recorded in config/processor.json."""
import os

from common import CONFIG, call, processor_name


def main():
    name = processor_name()
    call("DELETE", f"https://{name.split('/locations/')[1].split('/')[0]}-documentai.googleapis.com/v1/{name}")
    os.remove(CONFIG)
    print(f"deleted {name}")


if __name__ == "__main__":
    main()
