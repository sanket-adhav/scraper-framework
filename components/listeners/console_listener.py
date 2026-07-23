from __future__ import annotations
#progress updates 
import typer
from core.events.types import Event


class ConsoleFeedbackListener:
    """Listens to pipeline events and prints user-friendly progress updates to the console."""

    def __call__(self, event: Event) -> None:
        payload = event.payload
        url = str(payload.get("url") or "")
        stage = payload.get("stage")

        if event.type == "stage.started":
            if stage == "fetch":
                short_url = url.split("?")[0]
                typer.echo(f"[*] Fetching: {short_url}...")
            elif stage == "discover":
                typer.echo(f"[*] Discovering circular links from listing page...")
        
        elif event.type == "record.extracted":
            title = payload.get("title")
            if title:
                typer.echo(f"[+] Extracted: {title}")
                
        elif event.type == "record.saved":
            filepath = payload.get("filepath")
            if filepath:
                typer.echo(f"[✓] Saved PDF to: {filepath}")
