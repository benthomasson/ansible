#!powershell
# This file is part of Ansible
#
# Ansible is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Ansible is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Ansible.  If not, see <http://www.gnu.org/licenses/>.

# WANT_JSON
# POWERSHELL_COMMON

# TODO: add check mode support

Set-StrictMode -Version 2
$ErrorActionPreference = "Stop"

$helper_def = @"
using System.Diagnostics;
using System.IO;
using System.Threading;

namespace Ansible.Shell
{
    public class ProcessUtil
    {
        public static void GetProcessOutput(StreamReader stdoutStream, StreamReader stderrStream, out string stdout, out string stderr)
        {
            var sowait = new EventWaitHandle(false, EventResetMode.ManualReset);
            var sewait = new EventWaitHandle(false, EventResetMode.ManualReset);

            string so = null, se = null;

            ThreadPool.QueueUserWorkItem((s)=>
            {
                so = stdoutStream.ReadToEnd();
                sowait.Set();
            });

            ThreadPool.QueueUserWorkItem((s) =>
            {
                se = stderrStream.ReadToEnd();
                sewait.Set();
            });

            foreach(var wh in new WaitHandle[] { sowait, sewait })
                wh.WaitOne();

            stdout = so;
            stderr = se;
        }
    }
}
"@

$params = Parse-Args $args -supports_check_mode $false

$raw_command_line = Get-AnsibleParam -obj $params -name "_raw_params" -type "str" -failifempty $true
$chdir = Get-AnsibleParam -obj $params -name "chdir" -type "path"
$executable = Get-AnsibleParam -obj $params -name "executable" -type "path"
$creates = Get-AnsibleParam -obj $params -name "creates" -type "path"
$removes = Get-AnsibleParam -obj $params -name "removes" -type "path"

$raw_command_line = $raw_command_line.Trim()

$result = @{
    changed = $true
    cmd = $raw_command_line
}

If($creates -and $(Test-Path $creates)) {
    Exit-Json @{msg="skipped, since $creates exists";cmd=$raw_command_line;changed=$false;skipped=$true;rc=0}
}

If($removes -and -not $(Test-Path $removes)) {
    Exit-Json @{msg="skipped, since $removes does not exist";cmd=$raw_command_line;changed=$false;skipped=$true;rc=0}
}

Add-Type -TypeDefinition $helper_def

$exec_args = $null

If(-not $executable -or $executable -eq "powershell") {
    $exec_application = "powershell"

    # force input encoding to preamble-free UTF8 so PS sub-processes (eg, Start-Job) don't blow up
    $raw_command_line = "[Console]::InputEncoding = New-Object Text.UTF8Encoding `$false; " + $raw_command_line

    # Base64 encode the command so we don't have to worry about the various levels of escaping
    $encoded_command = [Convert]::ToBase64String([System.Text.Encoding]::Unicode.GetBytes($raw_command_line))

    $exec_args = @("-noninteractive", "-encodedcommand", $encoded_command)
}
Else {
    # FUTURE: support arg translation from executable (or executable_args?) to process arguments for arbitrary interpreter?
    $exec_application = $executable
    $exec_args = @("/c", $raw_command_line)
}

$proc = New-Object System.Diagnostics.Process
$psi = $proc.StartInfo
$psi.FileName = $exec_application
$psi.Arguments = $exec_args
$psi.RedirectStandardOutput = $true
$psi.RedirectStandardError = $true
$psi.UseShellExecute = $false

If ($chdir) {
    $psi.WorkingDirectory = $chdir
}

$start_datetime = [DateTime]::UtcNow

Try {
    $proc.Start() | Out-Null # will always return $true for non shell-exec cases
}
Catch [System.ComponentModel.Win32Exception] {
    # fail nicely for "normal" error conditions
    # FUTURE: this probably won't work on Nano Server
    $excep = $_
    Exit-Json @{msg = $excep.Exception.Message; cmd = $raw_command_line; changed = $false; rc = $excep.Exception.NativeErrorCode}
}

$stdout = $stderr = [string] $null

[Ansible.Shell.ProcessUtil]::GetProcessOutput($proc.StandardOutput, $proc.StandardError, [ref] $stdout, [ref] $stderr) | Out-Null

$result.stdout = $stdout
$result.stderr = $stderr

# TODO: decode CLIXML stderr output (and other streams?)

$proc.WaitForExit() | Out-Null

$result.rc = $proc.ExitCode

$end_datetime = [DateTime]::UtcNow

$result.start = $start_datetime.ToString("yyyy-MM-dd hh:mm:ss.ffffff")
$result.end = $end_datetime.ToString("yyyy-MM-dd hh:mm:ss.ffffff")
$result.delta = $($end_datetime - $start_datetime).ToString("h\:mm\:ss\.ffffff")

Exit-Json $result
