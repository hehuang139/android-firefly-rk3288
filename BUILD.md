# Building the source release

This branch carries an uninstalled live-TV/audio candidate. Follow
[the candidate instructions](docs/live-channel-audio-candidate.md) for its
four-library FFmpeg build and separate launcher build. The historical accepted
firmware and candidate runtime validation are recorded separately.

Use x86_64 Linux, Docker, Git/repo, Python 3, make, patch, curl, xz, ripgrep,
dtc and an ARM hard-float cross compiler (`arm-linux-gnueabihf-*`). The Android
build uses its pinned Clang/Bionic toolchain. Budget roughly 64 GB RAM and
400 GB free storage. Commands below create ordinary files; they do not flash.

## 1. Source layout

Place this repository and `aosp/` next to each other in one work directory.
The checkout's name is arbitrary. Run in Bash from this repository:

```bash
export PORT_ROOT=$(pwd -P)
export FIREFLY_WORK_ROOT=$(dirname -- "$PORT_ROOT")
mkdir -p "$FIREFLY_WORK_ROOT/aosp" "$FIREFLY_WORK_ROOT/downloads"
cd "$FIREFLY_WORK_ROOT/aosp"
repo init -u https://android.googlesource.com/platform/manifest -b android-17.0.0_r1 --git-lfs
cp "$PORT_ROOT/manifests/aosp-pinned.xml" .repo/manifests/firefly-pinned.xml
repo init -m firefly-pinned.xml --git-lfs
repo sync -c -j4 --fail-fast
```

The manifest pins each AOSP project. Third-party FFmpeg and U-Boot commits and
checksums are documented in THIRD_PARTY.md and their build scripts. Do not copy
private SSH helpers, credentials, signing keys, APKs or userdata into this tree.

## 2. Final kernel and eMMC loader

```bash
cd "$PORT_ROOT"
curl -fL https://cdn.kernel.org/pub/linux/kernel/v6.x/linux-6.18.60.tar.xz   -o "$FIREFLY_WORK_ROOT/downloads/linux-6.18.60.tar.xz"
export FIREFLY_KERNEL_ARCHIVE="$FIREFLY_WORK_ROOT/downloads/linux-6.18.60.tar.xz"
export FIREFLY_KERNEL_OUTPUT="$FIREFLY_WORK_ROOT/kernel-release"
bash build.sh kernel
docker build -t firefly-rk3288-uboot-builder:local bootloader/source
bash variants/emmc/rebuild.sh
```

`kernel-release` must not exist beforehand. `kernel/final/build-kernel.sh`
checks the upstream tar hash, applies the cumulative patch once, checks the
complete .config, compiles zImage and reconstructs the final DTS. The entry
stages zImage and the eMMC DTB into device build inputs. The small Hantro DMA
patch under patches/kernel is explanatory and already included; do not apply
it again. The DTS is decompiled corresponding source, not original labels.
DTC round-trip was byte-identical with DTC 1.7.2-g52f07dcc but gives warnings;
it is not DT schema validation. Kernel full rebuild reproducibility is untested.

The old TF scripts/configuration are retained for reference. The final tested
profile is eMMC and uses the standalone final DTS. Do not substitute the old
HEVC-enabled DTS or claim TF final-image testing from these instructions.

## 3. Android graphics and FFmpeg prerequisites

```bash
cd "$PORT_ROOT"
bash graphics/host-tools/build.sh "$FIREFLY_WORK_ROOT/aosp" "$FIREFLY_WORK_ROOT/tools/mesa-native"
bash build.sh install
```

`install` copies the board/graphics source and applies pinned adbd, Soong, hosts,
minigbm and NetBpfLoad patches. It rejects unrelated edits and verifies the exact
minigbm/NetBpfLoad before and after hashes. Existing private overlays are not
an acceptable substitute for these sources.

FFmpeg libraries are built separately before the full product. In the Android
builder environment, source `build/envsetup.sh`, select
`aosp_firefly_rk3288-aosp_current-userdebug`, and build `ndk_sysroot crtbegin_so
crtbegin_dynamic crtend_so crtend_android`. Then run:

```bash
python3 "$PORT_ROOT/device/firefly/rk3288/media/build-ffmpeg.py"   --aosp "$FIREFLY_WORK_ROOT/aosp" --work "$FIREFLY_WORK_ROOT/ffmpeg-release"
bash "$PORT_ROOT/build.sh" install
```

The script downloads the pinned Kwiboo FFmpeg commit, applies the checked-in
Android V4L2 Request patch, records configure options in its command, builds
the shared libraries and copies them into the board source. A clean Soong graph
may need these declared prebuilts generated before resolving the entire
product; this bootstrap sequence has not been repeated for the public profile.
Do not replace the missing libraries with unrelated FFmpeg binaries.

## 4. Build and assemble

```bash
cd "$PORT_ROOT"
bash build.sh graph
bash build.sh build
bash build.sh image-emmc
```

Outputs go to `../tvbox-artifacts/` under FIREFLY_WORK_ROOT. Whole-disk raw
images are 12 GiB even though zero-filled areas compress well. eMMC must be
large enough. No third-party APK or stream is required by this public profile.
Optional APK and direct authorized media hooks are in `apps/` and `tv-data/`.

The historical image validators and `finish-tvbox.py` encode an older product
with bundled apps/channels; the aggregate pipeline deliberately refuses to
run until those assertions are rebaselined for this public profile. Do not
report its old check counts as a fresh public build. Before distribution, run
a clean product build, audit all partitions, boot the target board, verify
audio/video and recheck the optional media policy. This source integration
does not claim that full validation has already occurred.

## Source-only checks

`docs/source-validation.json` records the checks actually performed during
export. Upstream kernel patch replay and final changed-file hashes are under
kernel/final. Provenance under docs/provenance records historical input hashes;
public-profile changes (empty media, disabled provider hook, portability) are
separate from those historical tested inputs.
