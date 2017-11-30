#!/usr/bin/python
import boto3
import argparse
import os
import subprocess
import sys
ec2 = ''
ssm = ''
banner = """
###########################################################################
 _______ ______ ______     _  _  _                 _         _             
(_______) _____|_____ \   | || || |      _        | |       | |            
 _____ | /       ____) )  | || || | ____| |_  ____| | _   _ | | ___   ____ 
|  ___)| |      /_____/   | ||_|| |/ _  |  _)/ ___) || \ / || |/ _ \ / _  |
| |____| \_____ _______   | |___| ( ( | | |_( (___| | | ( (_| | |_| ( ( | |
|_______)______|_______)   \______|\_||_|\___)____)_| |_|\____|\___/ \_|| |
                                                                    (_____|
###########################################################################
                                                                    
This script will utilize SSM to drop a Powershell script on the specified
Windows EC2 instance as well as create a repeated scheduled task if needed.
For all Powershell required arguments please use quotations.
Services are space seperated if sending more than one to CloudWatch. 
                                                                    
e.g.

./watchdog_generator.py -p PROFILE -r REGION -i INSTANCE -s "Service One" "Service Two" -f "c:\services.ps1" -e "Namespace" -m "Metric"

"""

def credential_check():
    global ec2, ssm
    awscreds = os.path.expanduser('~/.aws/credentials')
    if not os.path.exists(awscreds):
        print("No credentials were found.  Executing 'awsconfig'")
        print("Please provide your AWS profile credentials\n")
        AWSCONFIG = "aws configure"
        subprocess.call(AWSCONFIG, shell=True)
    else:
        session = boto3.session.Session(profile_name=args.profile, region_name=args.region)
        ec2 = session.resource('ec2')
        ssm = session.client('ssm')

def create_watchdog():
    services = tuple(args.services)
    print("Sending the following to %s...") % (args.instance)
    script = """$watchdog = "Import-Module AWSPowerShell
                    `$winsvcs = {svc}
                    `$dimension = New-Object Amazon.CloudWatch.Model.Dimension
                    `$dimension.Name = ""{dN}""
                    `$metric = New-Object Amazon.CloudWatch.Model.MetricDatum
                    `$metric.MetricName = ""{metric}""
                    `$metric.Unit = ""Count""

                    foreach (`$svc in `$winsvcs) 
                        {{
                 
                            `$status = Get-Service -Name `$svc; echo `$status.Status;

                            if (`$status.Status -eq ""Running"") {{`$count = ""1""}}

                            elseif

                                (`$status.Status -eq ""Stopped"") {{`$count = ""0""}}

                            `$dimension.Value = `$svc
                            `$metric.Timestamp = (Get-Date).ToUniversalTime()
                            `$metric.Value = `$count
                            `$metric.Dimensions = `$dimension
                            #Write-CWMetricData -Namespace ""{ns}"" -MetricData `$metric
                
                        }}"; echo $watchdog | Out-File "{filename}"; Get-Content "{filename}"
                        """.format(svc=services, dN=get_tag(args.instance), ns=args.namespace, filename=args.filename, metric=args.metric)
    print(script)

    ssmPStrendCheck = ssm.send_command(
            InstanceIds = [
            args.instance
        ],
        DocumentName = 'AWS-RunPowerShellScript',
        TimeoutSeconds = 60,
        Comment = 'Creating watchdog script for Windows service',
        Parameters = {
            'commands': [
                script
            ]
        })


def create_task():
    if args.task == None or args.description == None:
        print("Check arguments.  Taskname and/or description are not defined.")
        quit()
    scheduler = """
                $action = New-ScheduledTaskAction -Execute 'Powershell.exe' -Argument '-ExecutionPolicy Bypass "{path}"'; 
                $trigger =  New-ScheduledTaskTrigger -Once -At (Get-Date).Date -RepetitionInterval (New-TimeSpan -Minutes 5) -RepetitionDuration ([timeSpan]::maxvalue); 
                $settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -RunOnlyIfNetworkAvailable -DontStopOnIdleEnd; 
                Register-ScheduledTask -TaskName "{taskname}" -Description "{description}" -Settings $settings -Action $action -Trigger $trigger -RunLevel Highest -User SYSTEM
                """.format(path=args.filename, taskname=args.task, description=args.description)
    print(scheduler)

    ssmPStrendCheck = ssm.send_command(
            InstanceIds = [
            args.instance
        ],
        DocumentName = 'AWS-RunPowerShellScript',
        TimeoutSeconds = 60,
        Comment = 'Creating scheduled task',
        Parameters = {
            'commands': [
                scheduler
            ]
        })

def get_tag(x):
    instances = ec2.instances.filter(InstanceIds=[x])
    keytag = ''
    for i in instances:
        for j in i.tags:
            if j['Key'] == 'Name':
                keytag = j['Value']
            if keytag == '':
                keytag = i.id
    return keytag

if __name__ == "__main__":
    print(banner)
    parser = argparse.ArgumentParser()
    
    requiredNamed = parser.add_argument_group('Required arguments')
    optionalNamed = parser.add_argument_group('Optional arguments')
    psNamed = parser.add_argument_group('Powershell arguments')
    
    requiredNamed.add_argument("-p", "--profile", help="AWS credential profile to be used", required=True)
    requiredNamed.add_argument("-r", "--region", help="AWS region to use", required=True)
    requiredNamed.add_argument("-i", "--instance", help="Instance ID to be targeted", required=True)
    
    psNamed.add_argument("-m", "--metric", help="Name of CloudWatch metric", required=True)
    psNamed.add_argument("-s", "--services", nargs='+', help="Service[s] to be sent to CloudWatch", required=True)
    psNamed.add_argument("-f", "--filename", help="Full path of with filename e.g c:\script.ps1", required=True)
    psNamed.add_argument("-n", "--namespace", help="CloudWatch namespace to use.", required=True)
    
    optionalNamed.add_argument("-t", "--task", help="Name of scheduled task to be created")
    optionalNamed.add_argument("-d", "--description", help="Description of scheduled task")
    args = parser.parse_args()
    credential_check()
    create_watchdog()
    answer = ''
    while answer != 'y' or answer != 'N':
        answer = raw_input("Shall I create a scheduled task as well? y/N ")
        if answer == 'y':
            create_task()
            break
        if answer == 'N':
            break
        else:
            continue
