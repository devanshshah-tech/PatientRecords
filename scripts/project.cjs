// npm entry points for the existing Python application, with no frontend rewrite.
const fs = require('node:fs');
const path = require('node:path');
const {spawnSync} = require('node:child_process');
const root = path.resolve(__dirname, '..');
const windows = process.platform === 'win32';
const venv = path.join(root, '.venv', windows ? 'Scripts/python.exe' : 'bin/python');
const python = process.env.PATIENTRECORDS_PYTHON || (fs.existsSync(venv) ? venv : windows ? 'python' : 'python3');
const env = {...process.env};
function run(args) {
  const result = spawnSync(python, args, {cwd:root, env, stdio:'inherit'});
  if (result.error) { console.error(`Unable to start Python: ${result.error.code}`); process.exit(1); }
  if (result.status !== 0) process.exit(result.status || 1);
}
switch (process.argv[2]) {
  case 'build':
    run(['manage.py', 'check']);
    run(['manage.py', 'makemigrations', '--check', '--dry-run', '--noinput']);
    run(['manage.py', 'collectstatic', '--noinput']);
    console.log('Django build passed: system checks, migration consistency, static assets.');
    break;
  case 'test':
    // Unit tests never pick up the linked production URL from dotenv or the shell.
    env.DJANGO_LOAD_ENV_FILES = 'false';
    env.DJANGO_DEBUG = 'true';
    env.DJANGO_SETTINGS_MODULE = 'patientrecords.settings';
    delete env.DATABASE_URL; delete env.DATABASE_URL_UNPOOLED; delete env.DB_NAME;
    delete env.DJANGO_DATABASE_UNPOOLED;
    run(['manage.py', 'test', 'users', 'patientrecords.tests', '--noinput']);
    break;
  case 'start':
    run(['scripts/serve.py']);
    break;
  case 'migrate':
    env.DJANGO_DATABASE_UNPOOLED = 'true';
    run(['manage.py', 'migrate', '--noinput']);
    break;
  default:
    console.error('Expected build, test, start or migrate.'); process.exit(1);
}
