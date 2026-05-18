"""Resolve the third merge conflict in app.py."""
import pathlib

app_path = pathlib.Path("src/regrisk/ui/app.py")
content = app_path.read_text()
lines = content.split("\n")

# Find the last conflict block (the one around line 226)
head_marker = None
equal_marker = None
end_marker = None

for i, line in enumerate(lines):
    if "<<<<<<< HEAD" in line:
        head_marker = i
        equal_marker = None
        end_marker = None
    elif "=======" in line and head_marker is not None and equal_marker is None:
        equal_marker = i
    elif ">>>>>>> feat/evaluation-metrics" in line and equal_marker is not None:
        end_marker = i
        break

assert head_marker is not None and end_marker is not None, "No conflict found"
print(f"Conflict: lines {head_marker+1}-{end_marker+1}")

# Replace with resolved content
new_lines = lines[:head_marker]
new_lines.append("        render_traceability_tab()")
new_lines.append("    with tab6:")
new_lines.append("        render_evaluation_tab()")
new_lines.extend(lines[end_marker + 1:])

app_path.write_text("\n".join(new_lines))
print("Done - conflict resolved")
