from setuptools import find_packages, setup

# Frappe apps are typically installed editable into the bench env.
# Keep metadata aligned with pyproject.toml.

setup(
    name="zatgo_core",
    version="0.2.2",
    description="ZatGo Core — API-only platform hub",
    author="ZatGo Innovation",
    packages=find_packages(),
    zip_safe=False,
    include_package_data=True,
    install_requires=[],
)
