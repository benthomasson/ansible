#!/bin/sh

set -eu

platform="$1"

env

cd ~/

if [ "${platform}" = "freebsd" ]; then
    pkg install -y curl

    if [ ! -f bootstrap.sh ]; then
        curl "https://raw.githubusercontent.com/mattclay/ansible-hacking/master/bootstrap.sh" -o bootstrap.sh -#
    fi

    chmod +x bootstrap.sh
    ./bootstrap.sh pip -y -q

    pkg install -y \
        bash \
        devel/ruby-gems \
        gtar \
        mercurial \
        rsync \
        ruby \
        subversion \
        sudo \
        zip
fi

pip install virtualenv

# Tests assume loopback addresses other than 127.0.0.1 will work.
# Add aliases for loopback addresses used by tests.

for i in 3 4 254; do
    ifconfig lo0 alias "127.0.0.${i}" up
done

ifconfig lo0

# Since tests run as root, we also need to be able to ssh to localhost as root.
sed -i '' 's/^# *PermitRootLogin.*$/PermitRootLogin yes/;' /etc/ssh/sshd_config

if [ "${platform}" = "freebsd" ]; then
    # Restart sshd for configuration changes and loopback aliases to work.
    service sshd restart
fi

# Generate our ssh key and add it to our authorized_keys file.
# We also need to add localhost's server keys to known_hosts.

if [ ! -f "${HOME}/.ssh/id_rsa.pub" ]; then
    ssh-keygen -q -t rsa -N '' -f "${HOME}/.ssh/id_rsa"
    cp "${HOME}/.ssh/id_rsa.pub" "${HOME}/.ssh/authorized_keys"
    for key in /etc/ssh/ssh_host_*_key.pub; do
        pk=$(cat "${key}")
        echo "localhost ${pk}" >> "${HOME}/.ssh/known_hosts"
    done
fi

# Improve prompts on remote host for interactive use.
cat << EOF > ~/.bashrc
alias ls='ls -G'
export PS1='\[\e]0;\u@\h: \w\a\]\[\033[01;32m\]\u@\h\[\033[00m\]:\[\033[01;34m\]\w\[\033[00m\]\$ '
cd ~/ansible/
EOF
