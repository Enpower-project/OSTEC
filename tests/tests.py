import subprocess
import sys
from pathlib import Path

def run_all_scripts(directory: str, report_file: str = "report.txt"):
    """Run all Python scripts in a directory, print ✔/✘, and save only tracebacks to one report file."""
    dir_path = Path(directory).resolve()
    this_script = Path(__file__).resolve()
    report_path = Path(report_file).resolve()

    scripts = sorted(
        [p for p in dir_path.glob("*.py") if p.resolve() != this_script],
    )

    if not scripts:
        print(f"No Python scripts found in {dir_path}")
        return

    print(f"Running {len(scripts)} scripts in {dir_path}:\n")

    report_lines = []

    for script in scripts:
        try:
            subprocess.run(
                [sys.executable, str(script)],
                capture_output=True,
                text=True,
                check=True
            )
            print(f"{script.name:<30} ✔")
        except subprocess.CalledProcessError as e:
            print(f"{script.name:<30} ✘")

            # Extract traceback only
            tb = ""
            if e.stderr:
                lines = e.stderr.splitlines()
                for i, line in enumerate(lines):
                    if line.startswith("Traceback (most recent call last):"):
                        tb = "\n".join(lines[i:])
                        break

            if not tb:  # fallback if no clean traceback found
                tb = e.stderr

            report_lines.append(
                f"=== {script.name} FAILED ===\n{tb}\n"
            )

    # Only write a file if there were errors
    if report_lines:
        report_path.write_text("\n".join(report_lines), encoding="utf-8")
        print(f"\nError report written to {report_path}")
    else:
        print("\nAll scripts ran successfully. No error report created.")

if __name__ == "__main__":
    run_all_scripts(".")
