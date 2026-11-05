"""Check the compiled engine and the target GPU without model weights."""
import argparse
import importlib.machinery
import importlib.util
import json
from pathlib import Path
import sys

import torch

parser = argparse.ArgumentParser()
parser.add_argument('--build-only', action='store_true')
args = parser.parse_args()
lock = json.loads(Path('/opt/build/versions.lock.json').read_text())
assert torch.__version__ == lock['torch_version'], torch.__version__
assert '.'.join(map(str, sys.version_info[:2])) == lock['python_version']
spec = importlib.util.find_spec('exllamav3_ext')
assert spec and any(spec.origin.endswith(suffix) for suffix in importlib.machinery.EXTENSION_SUFFIXES), 'Missing compiled extension'
print('Compiled extension:', spec.origin)
if args.build_only:
    print('Build artifact check: PASS; GPU execution pending')
    sys.exit(0)

matches = [i for i in range(torch.cuda.device_count()) if '9070 XT' in torch.cuda.get_device_name(i)]
assert len(matches) == 1, 'Expected exactly one visible RX 9070 XT'
torch.cuda.set_device(matches[0])
import exllamav3_ext
import exllamav3
from exllamav3.architecture.dflash2 import DFlash2Model
sys.path.insert(0, '/opt/src/tabbyAPI')
from common.config_models import TabbyConfigModel

x = torch.ones((1024, 1024), device=f'cuda:{matches[0]}')
y = x @ x
torch.cuda.synchronize()
assert torch.all(y == 1024).item()
print('Python:', sys.version.split()[0])
print('PyTorch:', torch.__version__, 'HIP:', torch.version.hip)
print('GPU:', torch.cuda.get_device_name(matches[0]))
print('ExLlamaV3 extension, DFlash2 architecture, TabbyAPI schema imports: PASS')
print('GPU matrix multiplication: PASS')
print('Model loading, generation, and DFlash2 drafting remain to be tested.')
