# DeckApp

A virtual macro-pad for Debian. Create customisable button grids that run shell commands.

## Install

Dependencies (Debian):

sudo apt install python3 python3-gi gir1.2-gtk-4.0 gir1.2-adw-1


From .deb:

sudo dpkg -i deckapp-*.deb


From source:

git clone https://github.com/prabhatm021/deckapp.git
cd deckapp
python3 run.py


## Usage

1. Click New Deck to create a deck
2. Open it, click Edit, then click any `+` cell to add a button
3. Set a label, command, and optional icon
4. Click Done and press your buttons

Buttons can be single (runs once) or toggle (ON/OFF commands, state remembered).

## License

[MIT](LICENSE)
