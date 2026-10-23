from setuptools import find_packages, setup

# Frappe apps are typically installed editable into the bench env.
# Keep metadata aligned with pyproject.toml.

setup(
    name="zatgo_core",
    version="0.4.0",
    description="ZatGo Core — platform hub: apps, settings, VanSaleX, industries and the client RPC",
    author="ZatGo Innovation",
    packages=find_packages(),
    zip_safe=False,
    include_package_data=True,
    install_requires=["qrcode[pil]", "anthropic>=1.0", "pypdf>=4.0", "python-docx>=1.1"],
)
