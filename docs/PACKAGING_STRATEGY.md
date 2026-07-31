# Scraper Framework: Packaging Strategy

This document explains the different ways the tech team can install and use the `scraper_framework` as a package. 

---

## Option 1: Direct Install (From Git or Local Folder)
The tech team installs the package directly from your GitHub repository or a local folder without building any special files.

**How to do it:**
```bash
pip install git+https://github.com/sanket-adhav/scraper-framework.git
```

**Advantages:**
- **Zero setup required.** You don't need to build any files.
- **Always up to date.** As soon as you push code to GitHub, they can install the latest changes.

**Disadvantages:**
- If they install it this way, it can be harder to lock down specific versions if you make breaking changes in the future.

---

## Option 2: Build a Wheel File (`.whl`)
You build a physical package file on your computer and send that file to the tech team (via Slack, email, or an internal drive).

**How to do it:**
Run `uv build` in your terminal. It will create a file like `scraper_framework-0.1.0.whl`. The tech team then installs that file:
```bash
pip install scraper_framework-0.1.0-py3-none-any.whl
```

**Advantages:**
- **Very stable.** Because it's a fixed file, the code will never accidentally change on them.
- **Private.** You don't need to upload your code to any servers.

**Disadvantages:**
- **Manual work.** Every time you update the scraper, you have to run `uv build` and send them the new file manually.

---

## Option 3: Public PyPI (The Global Standard)
You upload the package to the official, public Python Package Index (PyPI). Anyone in the world can install your framework!

**How to do it:**
```bash
# You build and publish it:
uv publish

# Tech team (or anyone) installs it:
pip install scraper-framework
```

**Advantages:**
- **Global Availability.** The absolute easiest way for anyone to install your library.
- **Great for Open Source.** Perfect if you want to share this project with the developer community.

**Disadvantages:**
- **It is public.** Your framework's source code becomes publicly accessible on the internet (which is bad if it contains private company secrets, but fine if the framework is meant to be open-source).

---

## Option 4: Private Package Registry (Recommended for Enterprise)
Similar to PyPI, but hosted on your company's private network (like AWS CodeArtifact or Sonatype Nexus). 

**How to do it:**
```bash
# Tech team simply runs:
pip install scraper-framework
```

**Advantages:**
- **Fully Automated & Secure.** Easy version control, but the code stays strictly within the company.

**Disadvantages:**
- Requires the DevOps team to spend time setting up the private registry server.

---

## My Simple English Plan for Packaging

If I were to suggest the best plan for the Compliance tech team, here is the step-by-step rollout:

### Phase 1: Start with Direct Git Install (Fastest)
1. You make sure all your code is pushed to GitHub.
2. The tech team goes into the Compliance app and adds this line to their `requirements.txt`:
   `git+https://github.com/sanket-adhav/scraper-framework.git@main`
3. Whenever their app deploys, it will automatically download your scraper package from GitHub. 
4. *Why?* This takes 5 seconds to set up and requires zero DevOps work.

### Phase 2: Decide on Public vs Private (Long-Term)
1. Once the scraper framework is heavily used in production, you must decide if the framework is Open Source or Private.
2. **If Open Source:** Publish it to Public PyPI (Option 3).
3. **If Private Company Tech:** Tell the DevOps team to create an internal PyPI server (Option 4).
4. The tech team changes their `requirements.txt` to simply say: `scraper-framework==1.0.0`.
5. *Why?* This is the industry standard for large companies and makes versioning much safer.
