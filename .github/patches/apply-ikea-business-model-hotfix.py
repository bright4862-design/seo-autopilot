from pathlib import Path

path = Path("scanner-api/app/review.py")
text = path.read_text()
old = '''        "ecommerce_specialty_retail": "catalog_or_ecommerce",\n        "saas_app_membership": "saas_or_member_app",\n    }'''
new = '''        "ecommerce_specialty_retail": "catalog_or_ecommerce",\n        "saas_app_membership": "saas_or_member_app",\n        "content_blog": "content_or_general_business",\n        "general": "content_or_general_business",\n    }'''
if text.count(old) != 1:
    raise RuntimeError(f"Expected one decisive business-model map, found {text.count(old)}")
path.write_text(text.replace(old, new, 1))
