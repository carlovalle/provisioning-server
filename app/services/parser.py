import re

def parse_show_version(output):
    version = None
    model = None

    # IOS version
    match = re.search(r"Version (\S+)", output)
    if match:
        version = match.group(1)

    # Model
    match = re.search(r"cisco\s+(\S+)\s+\(", output, re.IGNORECASE)
    if match:
        model = match.group(1)

    return model, version


def parse_show_inventory(output):
    pid = None
    description = None

    match = re.search(r'PID:\s*(\S+)', output)
    if match:
        pid = match.group(1)

    match = re.search(r'DESCR:\s*"(.*?)"', output)
    if match:
        description = match.group(1)

    return pid, description
