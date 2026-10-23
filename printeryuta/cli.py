"""
Command Line Interface for PrinterYuta.
Provides diagnostic tools, status dashboards, auto-healing commands,
and pre-flight print execution.
"""

from __future__ import annotations
import os
import subprocess
import sys
import time
import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from printeryuta import __version__
from printeryuta.core.detector import HardwareDetector
from printeryuta.core.cups_manager import CupsManager
from printeryuta.core.ccpd_manager import CcpdManager
from printeryuta.core.spooler_watchdog import SpoolerWatchdog
from printeryuta.core.optimizer import DocumentOptimizer
from printeryuta.daemon.service import PrinterYutaDaemon
from printeryuta.daemon.systemd_generator import SystemdGenerator

console = Console()


@click.group()
@click.version_option(version=__version__, prog_name="PrinterYuta")
def main():
    """PrinterYuta: Autonomous Linux Printing Optimizer & Self-Healing Daemon."""
    pass


@main.command()
def status():
    """Display comprehensive status of hardware, CUPS queues, and daemons."""
    detector = HardwareDetector()
    cups_mgr = CupsManager()
    ccpd_mgr = CcpdManager()

    report = detector.scan()
    queues = cups_mgr.parse_queues()
    cstatus = ccpd_mgr.get_status()

    # 1. Hardware Table
    hw_table = Table(title="[bold cyan]1. USB Hardware & Kernel Driver (usblp)[/bold cyan]")
    hw_table.add_column("Property", style="bold")
    hw_table.add_column("Value")

    hw_table.add_row("Kernel usblp Module", "[green]Loaded[/green]" if report.usblp_loaded else "[red]NOT Loaded[/red]")
    hw_table.add_row("Active /dev/usb/lp Nodes", ", ".join(report.active_lp_nodes) or "[yellow]None[/yellow]")
    hw_table.add_row("CAPT Symlinks", ", ".join(report.capt_symlinks) or "[yellow]None[/yellow]")

    if report.devices:
        for d in report.devices:
            status_style = "green" if d.driver_bound == "usblp" else "red"
            hw_table.add_row(
                f"Device: {d.model_name}",
                f"USB ID [bold]{d.vendor_id}:{d.product_id}[/bold] | Driver: [{status_style}]{d.driver_bound}[/{status_style}]"
            )
    else:
        hw_table.add_row("Connected Printers", "[yellow]No USB printers detected[/yellow]")

    console.print(hw_table)
    console.print()

    # 2. CUPS Queues Table
    cups_table = Table(title="[bold cyan]2. CUPS Spooler Queues[/bold cyan]")
    cups_table.add_column("Queue Name", style="bold")
    cups_table.add_column("State")
    cups_table.add_column("Device URI")
    cups_table.add_column("Default")
    cups_table.add_column("Health / Warnings")

    if queues:
        for qname, q in queues.items():
            state_style = "green" if q.state == "idle" else ("yellow" if q.state == "printing" else "red")
            warn = ""
            if q.is_toxic_duplicate:
                warn = "[bold red]TOXIC DUPLICATE (Hijacks usblp)[/bold red]"
            elif q.is_capt and not q.device_uri.startswith("ccp:"):
                warn = "[yellow]Wrong backend (Should be ccp:/...)[/yellow]"
            else:
                warn = "[green]OK[/green]"

            cups_table.add_row(
                q.name,
                f"[{state_style}]{q.state}[/{state_style}]",
                q.device_uri or "None",
                "[bold green]Yes[/bold green]" if q.is_default else "No",
                warn
            )
    else:
        cups_table.add_row("No queues", "-", "-", "-", "[yellow]No print queues registered[/yellow]")

    console.print(cups_table)
    console.print()

    # 3. CCPD Daemon Table
    ccpd_table = Table(title="[bold cyan]3. Canon CAPT Daemon (ccpd) & Sockets[/bold cyan]")
    ccpd_table.add_column("Component", style="bold")
    ccpd_table.add_column("Status")

    ccpd_table.add_row("ccpd.service", f"[{'green' if cstatus.is_running else 'red'}]{cstatus.service_state}[/]")
    ccpd_table.add_row("captmon backend process", f"[{'green' if cstatus.captmon_running else 'red'}]{'Running (PID ' + str(cstatus.captmon_pid) + ')' if cstatus.captmon_running else 'NOT running'}[/]")
    ccpd_table.add_row("Print Data Port 59687", f"[{'green' if cstatus.pdata_port_listening else 'red'}]{'Listening' if cstatus.pdata_port_listening else 'Closed'}[/]")
    ccpd_table.add_row("Status UI Port 59787", f"[{'green' if cstatus.ui_port_listening else 'yellow'}]{'Listening' if cstatus.ui_port_listening else 'Closed'}[/]")
    ccpd_table.add_row("FIFO Pipe (/var/ccpd/fifo0)", f"[{'green' if cstatus.fifo_is_valid else 'red'}]{'Valid FIFO' if cstatus.fifo_is_valid else ('Exists but invalid' if cstatus.fifo_exists else 'MISSING')}[/]")

    console.print(ccpd_table)
    console.print()

    # Summary Health Panel
    issues = list(cstatus.health_issues)
    if report.has_detached_usblp:
        issues.append("Kernel usblp driver is detached! Printer USB interface was claimed by usbfs or disconnected.")
    for q in queues.values():
        if q.is_toxic_duplicate:
            issues.append(f"Rogue duplicate queue '{q.name}' is registered and triggers USB disconnection.")

    if not issues:
        console.print(Panel("[bold green]System Health: EXCELLENT (All guards active, queues verified ready to print)[/bold green]", border_style="green"))
    else:
        issue_text = "\n".join(f"[bold red]•[/bold red] {i}" for i in issues)
        console.print(Panel(f"[bold yellow]Detected Issues ({len(issues)}):[/bold yellow]\n{issue_text}\n\n[bold cyan]Tip: Run 'printeryuta heal' to automatically fix all solvable issues.[/bold cyan]", border_style="yellow"))


@main.command()
def doctor():
    """Deep diagnostics with actionable recommendations."""
    console.print(Panel("[bold cyan]PrinterYuta Doctor: Deep Diagnostics Engine[/bold cyan]", border_style="cyan"))

    detector = HardwareDetector()
    cups_mgr = CupsManager()
    ccpd_mgr = CcpdManager()

    report = detector.scan()
    queues = cups_mgr.parse_queues()
    cstatus = ccpd_mgr.get_status()

    checks_passed = 0
    checks_total = 0

    def check(title: str, condition: bool, recommendation: str = ""):
        nonlocal checks_passed, checks_total
        checks_total += 1
        if condition:
            checks_passed += 1
            console.print(f"[bold green]✔ PASS[/bold green]: {title}")
        else:
            console.print(f"[bold red]✖ FAIL[/bold red]: {title}")
            if recommendation:
                console.print(f"       [yellow]Fix:[/yellow] {recommendation}")

    # Check 1: USB Detection
    check(
        "Printer physically detected on USB bus",
        len(report.devices) > 0,
        "Check USB cable, power switch, and ensure printer is turned ON."
    )

    # Check 2: usblp kernel module
    check(
        "Kernel module 'usblp' is active",
        report.usblp_loaded,
        "Run 'sudo modprobe usblp' to load printer kernel module."
    )

    # Check 3: Device node exists
    check(
        "Active character device node (/dev/usb/lp*) present",
        len(report.active_lp_nodes) > 0,
        "Unplug and re-plug USB cable or power-cycle printer to rebind usblp."
    )

    # Check 4: CUPS Scheduler
    check(
        "CUPS Print Spooler daemon is running",
        cups_mgr.is_cups_running(),
        "Run 'sudo systemctl restart cups'."
    )

    # Check 5: Toxic Duplicate Queues
    has_toxic = any(q.is_toxic_duplicate for q in queues.values())
    check(
        "No conflicting duplicate queues (e.g. LBP3300-2)",
        not has_toxic,
        "Run 'printeryuta heal' to purge conflicting queues."
    )

    # Check 6: CAPT Queue Backend
    capt_queues = [q for q in queues.values() if q.is_capt and not q.is_toxic_duplicate]
    valid_backend = all(q.device_uri.startswith("ccp:/var/ccpd/fifo0") for q in capt_queues) if capt_queues else True
    check(
        "Primary CAPT queue points to correct FIFO backend",
        valid_backend,
        "Run 'printeryuta heal' to re-point queue to ccp:/var/ccpd/fifo0."
    )

    # Check 7: CCPD Daemon
    check(
        "Canon CCPD daemon is active and running",
        cstatus.is_running,
        "Run 'sudo systemctl restart ccpd'."
    )

    # Check 8: captmon backend
    check(
        "captmon hardware communication handler is active",
        cstatus.captmon_running,
        "Restart CCPD after printer is powered on: 'sudo systemctl restart ccpd'."
    )

    # Check 9: FIFO pipe
    check(
        "Spool pipe /var/ccpd/fifo0 is valid and accessible",
        cstatus.fifo_is_valid,
        "Run 'printeryuta heal' to recreate the FIFO special file."
    )

    console.print()
    score = int((checks_passed / checks_total) * 100) if checks_total else 0
    color = "green" if score >= 90 else ("yellow" if score >= 60 else "red")
    console.print(f"Health Score: [{color}]{score}%[/] ({checks_passed}/{checks_total} checks passed)")


@main.command()
@click.option("--quiet", "-q", is_flag=True, help="Suppress detailed console output.")
def heal(quiet: bool):
    """Autonomously fix misconfigured queues, clean toxic devices, and reset spooler."""
    if not quiet:
        console.print("[bold cyan]Starting PrinterYuta Autonomous Healing Sequence...[/bold cyan]")

    cups_mgr = CupsManager()
    watchdog = SpoolerWatchdog(cups_manager=cups_mgr)

    # Step 1: Heal CUPS queues
    actions = cups_mgr.heal_capt_queues()
    for act in actions:
        if not quiet:
            console.print(f"[bold green]✔[/bold green] {act}")

    # Step 2: Reap stuck jobs and resume queues
    reaped = watchdog.scan_and_reap(purge_all_stuck=True)
    for wact in reaped:
        if not quiet:
            console.print(f"[bold green]✔[/bold green] Purged stuck job: {wact.target_id} on {wact.queue_name}")

    # Step 3: Check FIFO
    fifo_path = "/var/ccpd/fifo0"
    if not os.path.exists(fifo_path):
        try:
            os.makedirs(os.path.dirname(fifo_path), exist_ok=True)
            os.mkfifo(fifo_path)
            if not quiet:
                console.print(f"[bold green]✔[/bold green] Created FIFO pipe at {fifo_path}")
        except PermissionError:
            if not quiet:
                console.print(f"[bold yellow]![/bold yellow] Could not create {fifo_path} without root privileges.")

    if not quiet:
        console.print("[bold green]✔ Healing sequence complete![/bold green]")


@main.command()
@click.argument("filepath", type=click.Path(exists=True))
@click.option("--printer", "-p", default=None, help="Target printer queue name.")
@click.option("--grayscale/--color", "-g/-c", default=True, help="Convert to optimized monochrome grayscale.")
@click.option("--fit-a4/--no-fit", "-f", default=True, help="Force fit page to standard A4 paper.")
@click.option("--dpi", "-d", default=600, type=int, help="Target resolution DPI (default: 600).")
def print(filepath: str, printer: Optional[str], grayscale: bool, fit_a4: bool, dpi: int):
    """Smart print with pre-flight optimization and queue verification."""
    console.print(f"[bold cyan]PrinterYuta Smart Print:[/bold cyan] {filepath}")

    cups_mgr = CupsManager()
    optimizer = DocumentOptimizer()

    # Determine destination queue
    target_queue = printer or cups_mgr.get_default_destination()
    if not target_queue:
        queues = cups_mgr.parse_queues()
        if queues:
            target_queue = list(queues.keys())[0]
        else:
            console.print("[bold red]Error: No printer queues available on the system.[/bold red]")
            sys.exit(1)

    console.print(f"Target Queue: [bold]{target_queue}[/bold]")

    # Run auto-heal pre-flight
    cups_mgr.heal_capt_queues()

    # Pre-flight optimization if PDF
    file_to_print = filepath
    if filepath.lower().endswith(".pdf"):
        console.print("[cyan]Running pre-flight document optimization...[/cyan]")
        res = optimizer.optimize_pdf(
            input_pdf=filepath,
            target_dpi=dpi,
            grayscale=grayscale,
            fit_page=fit_a4
        )
        if res.is_modified:
            diff_kb = (res.original_size_bytes - res.optimized_size_bytes) // 1024
            console.print(f"[green]✔ Optimized PDF[/green] (Reduced by {diff_kb} KB, {', '.join(res.actions_taken)})")
            file_to_print = res.output_path

    # Submit job
    cmd = ["lp", "-d", target_queue, file_to_print]
    res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False)

    if res.returncode == 0:
        job_msg = res.stdout.strip()
        console.print(f"[bold green]✔ Print job submitted successfully![/bold green] ({job_msg})")
    else:
        console.print(f"[bold red]✖ Print failed:[/bold red] {res.stderr.strip()}")
        sys.exit(res.returncode)


@main.command()
@click.option("--printer", "-p", default=None, help="Target printer queue name.")
def testpage(printer: Optional[str]):
    """Generate and print an optimized diagnostic test page."""
    cups_mgr = CupsManager()
    optimizer = DocumentOptimizer()

    target_queue = printer or cups_mgr.get_default_destination() or "LBP3300"
    console.print(f"Generating diagnostic test page for [bold]{target_queue}[/bold]...")

    test_pdf = optimizer.generate_diagnostic_page(
        output_path="/tmp/printeryuta_diagnostic.pdf",
        printer_name=target_queue
    )

    console.print(f"Test page created at: [green]{test_pdf}[/green]")
    cmd = ["lp", "-d", target_queue, test_pdf]
    res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False)

    if res.returncode == 0:
        console.print(f"[bold green]✔ Test page dispatched to {target_queue}![/bold green]")
    else:
        console.print(f"[bold red]✖ Failed to dispatch test page:[/bold red] {res.stderr.strip()}")


@main.command()
@click.option("--interval", "-i", default=10, type=int, help="Polling interval in seconds.")
def daemon(interval: int):
    """Run the continuous background supervisor watchdog."""
    service = PrinterYutaDaemon(
        interval_seconds=interval,
        on_heal_event=lambda msg: console.print(f"[cyan][{time.strftime('%H:%M:%S')}][/cyan] {msg}")
    )
    try:
        service.start()
    except KeyboardInterrupt:
        service.stop()


@main.command()
def install_daemon():
    """Generate systemd units and udev rules for zero-touch auto-healing."""
    gen = SystemdGenerator()
    assets = gen.get_asset_paths()

    console.print(Panel("[bold cyan]PrinterYuta Zero-Touch System Installer[/bold cyan]", border_style="cyan"))

    udev_content = gen.generate_udev_rules()
    hotplug_content = gen.generate_hotplug_service()
    watchdog_content = gen.generate_watchdog_service()

    # Save generated files to repo assets directory
    repo_asset_dir = os.path.join(os.path.dirname(__file__), "assets")
    os.makedirs(os.path.join(repo_asset_dir, "udev"), exist_ok=True)
    os.makedirs(os.path.join(repo_asset_dir, "systemd"), exist_ok=True)

    with open(os.path.join(repo_asset_dir, "udev/85-printeryuta-canon.rules"), "w") as f:
        f.write(udev_content)

    with open(os.path.join(repo_asset_dir, "systemd/printeryuta-hotplug.service"), "w") as f:
        f.write(hotplug_content)

    with open(os.path.join(repo_asset_dir, "systemd/printeryuta-watchdog.service"), "w") as f:
        f.write(watchdog_content)

    console.print("[green]✔ Generated system assets in repo:[/green]")
    console.print(f"  - {os.path.join(repo_asset_dir, 'udev/85-printeryuta-canon.rules')}")
    console.print(f"  - {os.path.join(repo_asset_dir, 'systemd/printeryuta-hotplug.service')}")
    console.print(f"  - {os.path.join(repo_asset_dir, 'systemd/printeryuta-watchdog.service')}")
    console.print()
    console.print("[bold yellow]To activate system-wide zero-touch printing on Ubuntu, run:[/bold yellow]")
    console.print("""
sudo cp printeryuta/assets/udev/85-printeryuta-canon.rules /etc/udev/rules.d/
sudo cp printeryuta/assets/systemd/*.service /etc/systemd/system/
sudo udevadm control --reload-rules && sudo udevadm trigger
sudo systemctl daemon-reload
sudo systemctl enable --now printeryuta-watchdog.service
""")


if __name__ == "__main__":
    main()
