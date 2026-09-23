import argparse
import hashlib
import os
import re
import shutil
import subprocess
from pathlib import Path

from app_build import BuildVariant, add_variant_argument

root = Path(__file__).resolve().parents[1]

# Windows 版本沿用原内部产品标识与数据目录，两版共用同一个安装标识。
APP_ID = '{{6F2B4C1A-9D3E-4F5B-8A7C-2E1D0B9F6A55}}'
ISCC_CANDIDATES = (
    Path('C:/Program Files (x86)/Inno Setup 6/ISCC.exe'),
    Path('C:/Program Files/Inno Setup 6/ISCC.exe'),
    Path('C:/Program Files (x86)/Inno Setup 7/ISCC.exe'),
    Path('C:/Program Files/Inno Setup 7/ISCC.exe'),
)

TEMPLATE = '''; 由 scripts/build_installer.py 生成，不要手工修改。
[Setup]
AppId={app_id}
AppName={app_name}
AppVersion={app_version}
AppVerName={app_name} {app_version}
AppPublisher={app_name}
VersionInfoVersion={numeric_version}
VersionInfoDescription={app_name} 安装程序
DefaultDirName={{autopf}}\\{slug}
DefaultGroupName={app_name}
DisableProgramGroupPage=yes
AllowNoIcons=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
MinVersion=10.0
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
OutputDir={output_dir}
OutputBaseFilename={output_base}
SetupIconFile={icon}
UninstallDisplayIcon={{app}}\\{exe_name}
UninstallDisplayName={app_name} {app_version}

[Tasks]
Name: "desktopicon"; Description: "{{cm:CreateDesktopIcon}}"; GroupDescription: "{{cm:AdditionalIcons}}"; Flags: unchecked

[Files]
Source: "{staging}\\*"; DestDir: "{{app}}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{{autoprograms}}\\{app_name}"; Filename: "{{app}}\\{exe_name}"
Name: "{{autodesktop}}\\{app_name}"; Filename: "{{app}}\\{exe_name}"; Tasks: desktopicon

[Run]
Filename: "{{app}}\\{exe_name}"; Description: "{{cm:LaunchProgram,{app_name}}}"; Flags: nowait postinstall skipifsilent
'''


def find_iscc(explicit):
    if explicit:
        return Path(explicit).expanduser()
    environment = os.environ.get('ISCC')
    if environment:
        return Path(environment)
    found = shutil.which('iscc')
    if found:
        return Path(found)
    for candidate in ISCC_CANDIDATES:
        if candidate.is_file():
            return candidate
    return None


def numeric_version(version):
    numbers = re.findall(r'\d+', version)
    padded = (numbers + ['0', '0', '0', '0'])[:4]
    return '.'.join(padded)


def write_checksums(output, version):
    checksums = []
    for artifact in sorted(output.glob(f'*-{version}-*')):
        if artifact.name == 'SHA256SUMS.txt' or not artifact.is_file():
            continue
        digest = hashlib.sha256()
        with artifact.open('rb') as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b''):
                digest.update(chunk)
        checksums.append(f'{digest.hexdigest()}  {artifact.name}')
    (output / 'SHA256SUMS.txt').write_text('\n'.join(checksums) + '\n', encoding='ascii')
    return checksums


def main():
    parser = argparse.ArgumentParser(description='把 Windows 发布目录打包成 Inno Setup 安装程序')
    parser.add_argument('--iscc', help='ISCC.exe 路径；默认读 ISCC 环境变量或常见安装位置')
    add_variant_argument(parser)
    options = parser.parse_args()
    variant = BuildVariant(options.all_sources)

    version = re.search(r'^version:\s*([\w.+-]+)\s*$', (root / 'pubspec.yaml').read_text(encoding='utf-8'), re.MULTILINE).group(1)
    bundle = root / 'build' / 'windows' / 'x64' / 'runner' / 'Release'
    executable = 'zhenguojian.exe'
    if not (bundle / executable).is_file():
        raise SystemExit('缺少 Windows 发布目录，请先运行 python scripts/build_windows.py：' + str(bundle))
    if not (bundle / 'data' / 'app.so').is_file():
        raise SystemExit('Windows 发布目录缺少 data/app.so：' + str(bundle))

    iscc = find_iscc(options.iscc)
    if not iscc or not iscc.is_file():
        raise SystemExit('未找到 Inno Setup 编译器 ISCC.exe，请用 --iscc 指定路径或设置 ISCC 环境变量。')

    exe_name = variant.slug + '.exe'
    staging = root / 'build' / 'installer' / variant.slug
    if staging.exists():
        shutil.rmtree(staging)
    shutil.copytree(bundle, staging)
    if exe_name != executable:
        (staging / executable).replace(staging / exe_name)

    icon = root / 'windows' / 'runner' / 'resources' / 'app_icon.ico'
    output = root / 'dist' / 'windows'
    output.mkdir(parents=True, exist_ok=True)
    output_base = f'{variant.slug}-{version}-windows-x64-setup'
    script = root / 'build' / 'installer' / f'{variant.slug}.iss'
    script.parent.mkdir(parents=True, exist_ok=True)
    script.write_text(TEMPLATE.format(
        app_id=APP_ID,
        app_name=variant.name,
        app_version=version,
        numeric_version=numeric_version(version),
        slug=variant.slug,
        output_dir=output,
        output_base=output_base,
        icon=icon,
        exe_name=exe_name,
        staging=staging,
    ), encoding='utf-8')

    subprocess.run([str(iscc), '/Qp', str(script)], check=True)
    artifact = output / f'{output_base}.exe'
    if not artifact.is_file():
        raise SystemExit('未生成安装程序：' + str(artifact))
    for line in write_checksums(output, version):
        print(line)
    print(artifact)


if __name__ == '__main__':
    main()
