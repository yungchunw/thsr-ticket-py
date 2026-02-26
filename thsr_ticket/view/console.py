import sys
import questionary
from rich.console import Console

# Use stderr so rich doesn't conflict with questionary (prompt_toolkit) on stdout
console = Console(stderr=True)

# Use foreground-only colors to avoid background-color clearing issues in some terminals
QUESTIONARY_STYLE = questionary.Style([
    ('qmark', 'fg:cyan bold'),
    ('question', 'bold'),
    ('answer', 'fg:yellow bold'),
    ('pointer', 'fg:cyan bold'),
    ('highlighted', 'fg:cyan bold'),
    ('instruction', 'fg:grey'),
])
