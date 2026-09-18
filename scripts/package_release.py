"""Create a source-only ZIP from an explicit allowlist, never runtime data."""
from pathlib import Path
import re
import zipfile


ROOT = Path(__file__).resolve().parents[1]
FILES = (
    '.env.example', '.gitignore', '.gitattributes', '.dockerignore',
    'README.md', 'LICENSE', 'CONTRIBUTING.md', 'VALIDATION.md',
    'Dockerfile', 'docker-compose.yml', 'requirements.txt', 'main.py', 'config.py',
    'data/.gitkeep', '.github/pull_request_template.md',
    '.github/workflows/tests.yml',
)


def main():
    paths = [ROOT / name for name in FILES]
    for directory, pattern in [('src', '*.py'), ('tests', '*.py'),
                               ('scripts', '*.py'), ('docs', '*.md')]:
        paths.extend(sorted((ROOT / directory).glob(pattern)))
    # Check for accidental copies of this user's actual credentials without
    # logging values or including .env in the archive.
    secrets = []
    env = ROOT / '.env'
    if env.exists():
        for line in env.read_text(encoding='utf-8-sig').splitlines():
            key, sep, value = line.partition('=')
            if sep and any(word in key.upper() for word in ('KEY', 'TOKEN', 'SECRET', 'WEBHOOK', 'PASSWORD')):
                value = value.strip().strip('"\'')
                if len(value) >= 8:
                    secrets.append(value.encode())
    entries = []
    for path in paths:
        if path.is_symlink() or not path.is_file():
            raise ValueError(f'Missing or symlinked source file: {path.name}')
        relative = path.relative_to(ROOT).as_posix()
        content = path.read_bytes()
        if any(secret in content for secret in secrets):
            raise ValueError(f'Private credential found in {relative}; archive not created')
        if re.search(rb'https://(?:discord(?:app)?\.com)/api/webhooks/\d+/[A-Za-z0-9_-]+', content):
            raise ValueError(f'Webhook credential found in {relative}; archive not created')
        entries.append((relative, content))
    destination = ROOT / 'dist' / 'cs2-tradeup-bot.zip'
    destination.parent.mkdir(exist_ok=True)
    with zipfile.ZipFile(destination, 'w', zipfile.ZIP_DEFLATED) as archive:
        for relative, content in entries:
            archive.writestr('cs2-tradeup-bot/' + relative, content)
    print(f'Created {destination.name}: {len(entries)} source files; no runtime data included')


if __name__ == '__main__':
    main()
