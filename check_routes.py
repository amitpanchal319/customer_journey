from api.main import app
for route in app.routes:
    if hasattr(route, 'methods'):
        print(route.methods, route.path)