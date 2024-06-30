#!/usr/bin/env -S bash -e

# At first I attemped to download from jdk.java.net, download.java.net or downloads.oracle.com. 
# However I did not want archive releases that were too old, so I ended up using `apt` to install it.

sudo apt install openjdk-21-jdk
sudo apt install openjdk-17-jdk
sudo apt install openjdk-11-jdk
