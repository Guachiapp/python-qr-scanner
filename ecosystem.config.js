module.exports = {
    apps: [{
      name: 'guachi-qr-scanner',
      script: 'venv/bin/python',
      args: 'main.py',
      cwd: '/home/desarrollo/workspace/guachi-qr-scanner',
      interpreter: 'none',
      autorestart: true,
      watch: false,
      max_memory_restart: '500M',
      env: {
        PYTHONUNBUFFERED: '1'
      },
      error_file: './logs/err.log',
      out_file: './logs/out.log',
      log_date_format: 'YYYY-MM-DD HH:mm:ss Z'
    }]
  };