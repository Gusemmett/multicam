"""CSV file processing for stereo tracks."""

import subprocess
import pathlib
import logging


class CSVProcessor:
    """Handles CSV file cutting and synchronization."""

    @staticmethod
    def process_csv(
        csv_path: str,
        output_path: str,
        cut_ns: int,
        limit_ns: int
    ):
        """Process CSV file with timestamp cutting.

        Args:
            csv_path: Input CSV file path
            output_path: Output CSV file path
            cut_ns: Cut time in nanoseconds
            limit_ns: Duration limit in nanoseconds
        """
        # AWK command that preserves all columns
        awk_cmd = [
            "awk", "-F,", f"-v", f"CUT_NS={cut_ns}", f"-v", f"LIMIT_NS={limit_ns}",
            'NR==1 {print $0; next} { ts=$1+0; if (ts>=CUT_NS && ts < CUT_NS+LIMIT_NS) { printf "%d", ts-CUT_NS; for(i=2; i<=NF; i++) printf ",%s", $i; printf "\\n" } }',
            csv_path
        ]

        with open(output_path, "w") as f:
            result = subprocess.run(awk_cmd, stdout=f, capture_output=False)

        if result.returncode != 0:
            logging.error(f"Failed to process CSV {csv_path}")

    @staticmethod
    def process_stereo_csvs(
        track: dict,
        output_dir: str | None,
        cut_us: int,
        duration_us: int,
        replace_files: bool
    ) -> list[tuple[str, str]]:
        """Process all CSV files for a stereo track.

        Args:
            track: Track dictionary with csv_files list
            output_dir: Output directory (if not replacing)
            cut_us: Cut time in microseconds
            duration_us: Duration in microseconds
            replace_files: Whether to replace original files

        Returns:
            List of (temp_path, original_path) tuples if replace_files=True, else empty list
        """
        cut_ns = int(cut_us * 1000)
        limit_ns = int(duration_us * 1000)

        # Get list of CSV files from track
        csv_files = track.get("csv_files", [])
        files_to_replace = []

        for csv_path in csv_files:
            p_csv = pathlib.Path(csv_path)

            # Determine output path for CSV
            if replace_files:
                # Write to temp file with -synced suffix
                out_csv_name = p_csv.stem + "-synced" + p_csv.suffix
                out_csv = str(p_csv.parent / out_csv_name)
                files_to_replace.append((out_csv, str(p_csv)))
            else:
                out_csv_name = p_csv.stem + "-synced" + p_csv.suffix
                out_csv = str(pathlib.Path(output_dir) / out_csv_name)

            CSVProcessor.process_csv(csv_path, out_csv, cut_ns, limit_ns)
            logging.info(f"Processed CSV: {p_csv.name}")

        return files_to_replace
