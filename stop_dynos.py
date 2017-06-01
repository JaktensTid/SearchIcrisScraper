import os
import subprocess

for i in range(1, 5):
	proc = subprocess.Popen('heroku ps --app searchicrisscraper' + str(i),shell=True, stdout=subprocess.PIPE)
	res = proc.stdout.read()
	res = res.decode('utf-8').split(' ')
	run = list([item for item in res if 'run.' in item])
	if not run:
		continue
	run = int(run[-1].split('.')[-1])
	print('heroku stop run.%s --app searchicrisscraper%s' % (run, i))
	proc = subprocess.Popen('heroku stop run.%s --app searchicrisscraper%s' % (run, i),shell=True, stdout=subprocess.PIPE)
