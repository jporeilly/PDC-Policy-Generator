# Render every mermaid block in the docs to its canonical PNG in images/.
# The markdown keeps the LIVE mermaid (GitHub renders it natively); these
# PNGs are generated artifacts — used by build-docx.py to embed diagrams in
# lab-setup.docx, and available for decks. Re-run after editing a diagram so
# the PNGs can never drift from the blocks.
#
#   python render-diagrams.py          (requires node/npx; uses mermaid-cli)
import io, os, re, shutil, subprocess, sys, tempfile

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
IMAGES = os.path.join(ROOT, "images")

# (markdown file, [png name per mermaid block, in document order])
DIAGRAMS = [
    ("README.md",        ["pipeline-diagram-preview.png", "mechanisms-diagram-preview.png"]),
    ("docs/CONTRACT.md", ["contract-anatomy-preview.png", "contract-lifecycle-preview.png"]),
    ("docs/INSTALL.md",  ["install-topology-preview.png", "install-workflow-preview.png"]),
]

NPX = shutil.which("npx") or shutil.which("npx.cmd") or "npx"


def render(block, out_png):
    with tempfile.TemporaryDirectory() as td:
        mmd = os.path.join(td, "d.mmd")
        io.open(mmd, "w", encoding="utf-8", newline="\n").write(block)
        r = subprocess.run([NPX, "-y", "-q", "@mermaid-js/mermaid-cli",
                            "-i", mmd, "-o", out_png, "-s", "2", "-b", "white", "-q"],
                           capture_output=True, text=True, shell=(os.name == "nt"))
        if r.returncode != 0:
            raise RuntimeError(f"mmdc failed for {out_png}: {(r.stderr or r.stdout)[-300:]}")


def main():
    os.makedirs(IMAGES, exist_ok=True)
    built = 0
    for rel, names in DIAGRAMS:
        path = os.path.join(ROOT, rel)
        blocks = re.findall(r"```mermaid\n(.*?)```", io.open(path, encoding="utf-8").read(), re.S)
        if len(blocks) != len(names):
            print(f"  ! {rel}: {len(blocks)} mermaid block(s) but {len(names)} name(s) mapped — "
                  "update DIAGRAMS in render-diagrams.py")
        for block, name in zip(blocks, names):
            out = os.path.join(IMAGES, name)
            render(block, out)
            print(f"  rendered {rel} -> images/{name}")
            built += 1
    print(f"{built} diagram(s) rendered")


if __name__ == "__main__":
    sys.exit(main())
