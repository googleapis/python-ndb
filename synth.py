import synthtool as s
from synthtool import gcp

common = gcp.CommonTemplates()

# ----------------------------------------------------------------------------
# Add templated files
# ----------------------------------------------------------------------------
templated_files = common.py_library(unit_cov_level=100, cov_level=100)
s.move(templated_files / '.kokoro')  # just move kokoro configs

s.replace([".kokoro/publish-docs.sh", ".kokoro/build.sh"], "cd github/python-ndb", 
"""cd github/python-ndb

# Need enchant for spell check
sudo apt-get update
sudo apt-get -y install dictionaries-common aspell aspell-en \\
                        hunspell-en-us libenchant1c2a enchant""")

s.shell.run(["nox", "-s", "blacken"], hide_output=False)