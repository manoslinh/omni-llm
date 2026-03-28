"""
Simplified version of Mermaid animation generation to avoid f-string issues.
"""

import json
from pathlib import Path


def generate_execution_animation(
    snapshot_dir: str | Path,
    output_file: str | Path = "execution_animation.html",
) -> str:
    """Generate an HTML file that animates through execution snapshots.

    Args:
        snapshot_dir: Directory containing Mermaid snapshot files.
        output_file: Path to output HTML file.

    Returns:
        Path to the generated HTML file.
    """
    snapshot_dir = Path(snapshot_dir)
    output_file = Path(output_file)

    # Find all snapshot files
    snapshot_files = sorted(snapshot_dir.glob("*.mmd"))
    if not snapshot_files:
        snapshot_files = sorted(snapshot_dir.glob("*.json"))

    if not snapshot_files:
        raise ValueError(f"No snapshot files found in {snapshot_dir}")

    # Read snapshots
    snapshots = []
    for filepath in snapshot_files:
        with open(filepath, encoding="utf-8") as f:
            content = f.read()

        snapshots.append({
            "file": filepath.name,
            "content": content,
        })

    # Create simple HTML
    html = f"""<!DOCTYPE html>
<html>
<head>
    <title>Execution Animation - {snapshot_dir.name}</title>
    <script src="https://cdn.jsdelivr.net/npm/mermaid@10.6.1/dist/mermaid.min.js"></script>
    <style>
        body {{ font-family: sans-serif; margin: 20px; }}
        .container {{ max-width: 800px; margin: 0 auto; }}
        .controls {{ margin: 20px 0; }}
        .mermaid {{ border: 1px solid #ccc; padding: 10px; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>Execution Animation</h1>
        <p>Visualizing {len(snapshots)} snapshots</p>

        <div class="controls">
            <button onclick="prevSnapshot()">Previous</button>
            <button onclick="nextSnapshot()">Next</button>
            <span id="counter">1 / {len(snapshots)}</span>
        </div>

        <div id="mermaid"></div>
    </div>

    <script>
        const snapshots = {json.dumps(snapshots)};
        let currentIndex = 0;

        mermaid.initialize({{ startOnLoad: false }});

        function updateDisplay() {{
            const snapshot = snapshots[currentIndex];
            document.getElementById('counter').textContent =
                `${{currentIndex + 1}} / ${{snapshots.length}}`;

            const container = document.getElementById('mermaid');
            container.innerHTML = '<div class="mermaid">' + snapshot.content + '</div>';

            mermaid.init(undefined, container.querySelector('.mermaid'));
        }}

        function prevSnapshot() {{
            if (currentIndex > 0) {{
                currentIndex--;
                updateDisplay();
            }}
        }}

        function nextSnapshot() {{
            if (currentIndex < snapshots.length - 1) {{
                currentIndex++;
                updateDisplay();
            }}
        }}

        // Initial display
        updateDisplay();
    </script>
</body>
</html>"""

    # Save HTML file
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(html)

    return str(output_file)
