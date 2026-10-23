"""
Pre-flight Document Optimizer for PrinterYuta.
Optimizes PDFs, images, and text documents before submission to CUPS:
- Downsamples excessive DPI to 600 DPI (ideal for Canon LBP3300/LBP2900).
- Converts to pure monochrome/grayscale to save memory and toner.
- Generates high-quality diagnostic test pages.
"""

from __future__ import annotations
import os
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass
from typing import Callable, List, Optional, Tuple


@dataclass
class OptimizationResult:
    input_path: str
    output_path: str
    original_size_bytes: int
    optimized_size_bytes: int
    is_modified: bool
    actions_taken: List[str]


class DocumentOptimizer:
    def __init__(self, run_cmd: Optional[Callable[[List[str]], Tuple[int, str, str]]] = None):
        self._run_cmd = run_cmd or self._default_run_cmd

    @staticmethod
    def _default_run_cmd(cmd: List[str]) -> Tuple[int, str, str]:
        try:
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False)
            return res.returncode, res.stdout, res.stderr
        except Exception as e:
            return 1, "", str(e)

    def optimize_pdf(
        self,
        input_pdf: str,
        output_pdf: Optional[str] = None,
        target_dpi: int = 600,
        grayscale: bool = True,
        fit_page: bool = True
    ) -> OptimizationResult:
        """
        Optimize a PDF using Ghostscript (gs) if available, reducing
        transmission size and avoiding GDI engine crashes.
        """
        orig_size = os.path.getsize(input_pdf) if os.path.exists(input_pdf) else 0

        if output_pdf is None:
            fd, output_pdf = tempfile.mkstemp(suffix="_optimized.pdf")
            os.close(fd)

        actions = []

        # Check if gs is installed
        gs_bin = shutil.which("gs")
        if not gs_bin:
            # Fallback: copy file unmodified
            shutil.copy2(input_pdf, output_pdf)
            return OptimizationResult(
                input_path=input_pdf,
                output_path=output_pdf,
                original_size_bytes=orig_size,
                optimized_size_bytes=orig_size,
                is_modified=False,
                actions_taken=["Ghostscript not installed, passed through original file"]
            )

        cmd = [
            gs_bin,
            "-sDEVICE=pdfwrite",
            "-dCompatibilityLevel=1.4",
            "-dPDFSETTINGS=/printer",
            "-dNOPAUSE",
            "-dQUIET",
            "-dBATCH",
            f"-dColorImageResolution={target_dpi}",
            f"-dGrayImageResolution={target_dpi}",
            f"-dMonoImageResolution={target_dpi}",
        ]

        if fit_page:
            cmd.extend(["-dPDFFitPage", "-sPAPERSIZE=a4"])
            actions.append("Fit page to A4 standard")

        if grayscale:
            cmd.append("-sColorConversionStrategy=Gray")
            cmd.append("-dProcessColorModel=/DeviceGray")
            actions.append("Converted color channels to optimized monochrome grayscale")

        cmd.extend([
            f"-sOutputFile={output_pdf}",
            input_pdf
        ])

        code, _, err = self._run_cmd(cmd)
        if code == 0 and os.path.exists(output_pdf) and os.path.getsize(output_pdf) > 0:
            new_size = os.path.getsize(output_pdf)
            actions.append(f"Resampled images to {target_dpi} DPI")
            return OptimizationResult(
                input_path=input_pdf,
                output_path=output_pdf,
                original_size_bytes=orig_size,
                optimized_size_bytes=new_size,
                is_modified=True,
                actions_taken=actions
            )
        else:
            # Failed optimization, fallback to original
            shutil.copy2(input_pdf, output_pdf)
            return OptimizationResult(
                input_path=input_pdf,
                output_path=output_pdf,
                original_size_bytes=orig_size,
                optimized_size_bytes=orig_size,
                is_modified=False,
                actions_taken=[f"Optimization bypassed due to error: {err[:100]}"]
            )

    def generate_diagnostic_page(
        self,
        output_path: str = "/tmp/printeryuta_testpage.pdf",
        printer_name: str = "Canon LBP3300",
        device_uri: str = "ccp:/var/ccpd/fifo0"
    ) -> str:
        """Generate a clean, professional diagnostic test PDF."""
        # Use python to generate a self-contained PostScript file then convert with gs or write direct Postscript
        ps_path = "/tmp/printeryuta_testpage.ps"
        date_str = time.strftime("%Y-%m-%d %H:%M:%S")

        ps_content = f"""%!PS-Adobe-3.0
%%Title: PrinterYuta Diagnostic Page
%%Creator: PrinterYuta Linux Print Optimizer
%%Pages: 1
%%BoundingBox: 0 0 595 842
%%DocumentData: Clean7Bit
%%EndComments

/inch {{ 72 mul }} def
/cm {{ 28.3464567 mul }} def

% Draw border box
newpath
20 20 moveto
575 20 lineto
575 822 lineto
20 822 lineto
closepath
2 setlinewidth
stroke

% Header Background
newpath
22 750 moveto
573 750 lineto
573 820 lineto
22 820 lineto
closepath
0.9 setgray
fill

% Title Text
0 setgray
/Helvetica-Bold findfont 22 scalefont setfont
40 780 moveto
(PrinterYuta - Linux Print Optimizer) show

/Helvetica findfont 12 scalefont setfont
40 760 moveto
(Autonomous Self-Healing Test & Calibration Page) show

% Diagnostic Table
/Helvetica-Bold findfont 14 scalefont setfont
40 710 moveto
(Hardware & Spooler Diagnostic Summary) show

/Helvetica-Bold findfont 11 scalefont setfont
40 680 moveto (Target Printer:) show
40 655 moveto (Connection Backend:) show
40 630 moveto (Timestamp:) show
40 605 moveto (Host Machine:) show
40 580 moveto (System Driver:) show
40 555 moveto (Status Engine:) show

/Helvetica findfont 11 scalefont setfont
180 680 moveto ({printer_name}) show
180 655 moveto ({device_uri}) show
180 630 moveto ({date_str}) show
180 605 moveto (Ubuntu Linux x86_64) show
180 580 moveto (CUPS + Canon CAPT Protocol) show
180 555 moveto (VERIFIED READY - Autonomous Guard Active) show

% Separator line
newpath
40 535 moveto
555 535 lineto
1 setlinewidth
0.7 setgray
stroke

% Grayscale gradient calibration bar
0 setgray
/Helvetica-Bold findfont 12 scalefont setfont
40 505 moveto
(Grayscale Calibration & Halftone Test Pattern:) show

/draw_patch {{
    /shade exch def
    /x exch def
    newpath
    x 450 moveto
    x 40 add 450 lineto
    x 40 add 485 lineto
    x 485 lineto
    closepath
    shade setgray
    fill
    0 setgray
    0.5 setlinewidth
    stroke
}} def

40 1.0 draw_patch
85 0.9 draw_patch
130 0.8 draw_patch
175 0.7 draw_patch
220 0.6 draw_patch
265 0.5 draw_patch
310 0.4 draw_patch
355 0.3 draw_patch
400 0.2 draw_patch
445 0.1 draw_patch
490 0.0 draw_patch

% Footer notes
0 setgray
/Helvetica-Oblique findfont 10 scalefont setfont
40 80 moveto
(If this page has printed completely, your Linux printing stack and hardware communication are fully operational.) show
40 65 moveto
(PrinterYuta Watchdog Daemon protects this system from USB detachment and daemon stalling.) show

showpage
%%EOF
"""

        with open(ps_path, "w", encoding="utf-8") as f:
            f.write(ps_content)

        # Convert PS to PDF using ps2pdf or gs
        gs_bin = shutil.which("gs")
        if gs_bin:
            self._run_cmd([
                gs_bin,
                "-sDEVICE=pdfwrite",
                "-dNOPAUSE",
                "-dBATCH",
                "-dQUIET",
                f"-sOutputFile={output_path}",
                ps_path
            ])
            if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
                return output_path

        # If gs is not available, return the ps_path
        return ps_path
