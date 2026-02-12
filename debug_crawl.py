import json
from o3de_pilot.core.resolver import Resolver

r = Resolver()
r.resolve()
r.save()

# Check what each crawled repo contains
for url, data in r._crawled_remotes.items():
    if True:
        print(f"=== {url} ===")
        print(f"repo_name: {data.get('repo_name')}")
        for key in ["gems", "templates", "projects", "engines", "repos"]:
            val = data.get(key, [])
            if val:
                print(f"{key} ({len(val)}):")
                for v in val[:5]:
                    print(f"  {v}")
                if len(val) > 5:
                    print(f"  ... +{len(val)-5} more")
        for key in ["gems_data", "templates_data", "projects_data"]:
            val = data.get(key, [])
            if val:
                print(f"{key} ({len(val)}):")
                for v in val[:3]:
                    if isinstance(v, dict):
                        print(f"  name={v.get('gem_name', v.get('name','?'))}, display={v.get('display_name','')}")
                    else:
                        print(f"  {v}")
                if len(val) > 3:
                    print(f"  ... +{len(val)-3} more")
        print()
