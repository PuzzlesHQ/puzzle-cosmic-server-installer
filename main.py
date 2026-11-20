#!/usr/bin/env python3

import argparse
import hashlib
import urllib.request
import urllib.error
import json
from pathlib import Path
from urllib.error import HTTPError

GITHUB_OWNER = "PuzzlesHQ"
COSMIC_REPO = "puzzle-loader-cosmic"
CORE_REPO = "puzzle-loader-core"
GITHUB_BRANCH = "versioning"
GITHUB_LINK = "https://raw.githubusercontent.com"

CR_ARCHIVE_LINK = "https://raw.githubusercontent.com/PuzzlesHQ/CRArchive/refs/heads/main/versions.json"

PUZZLE_MAVEN_LINK = "https://maven.puzzleshq.dev/releases/"
JITPACK_LINK = "https://jitpack.io"
MAVEN_CENTRAL_LINK = "https://repo.maven.apache.org/maven2/"
MAVEN_CENTRAL_2_LINK = "https://repo1.maven.org/maven2/"

PUZZLE_INSTALLER_DIR = Path("puzzle_installer")
# OUTPUT_DIR
# CR_SERVER_JAR

RED = "\033[31m"
RESET = "\033[0m"


def download_json(url, file_name, refresh: bool = False) -> dict:
    file_path = PUZZLE_INSTALLER_DIR.joinpath(file_name + ".json")

    if refresh: file_path.unlink(missing_ok=True)

    if not file_path.exists():
        file_path.parent.mkdir(parents=True, exist_ok=True)
        with urllib.request.urlopen(url) as response:
            with open(file_path, "w") as f:
                f.write(response.read().decode())

    with open(file_path, "r") as file:
        return json.load(file)


def download_version_json(url, file_prefix, refresh: bool = False) -> dict:
    return download_json(url, file_prefix + "-" + "versions", refresh)


def download_repo_json(repo: str, refresh: bool = False) -> dict:
    url = f"{GITHUB_LINK}/{GITHUB_OWNER}/{repo}/{GITHUB_BRANCH}/versions.json"
    return download_version_json(url, repo, refresh)


def download_CR_version_json(refresh: bool = False) -> dict:
    return download_version_json(CR_ARCHIVE_LINK, "cr-archive", refresh)


def download_lib_json(url: str, prefix, refresh: bool = False) -> dict:
    return download_json(url, prefix + "-dependencies", refresh)


def print_versions():
    data = download_repo_json(CORE_REPO)
    versions = data["versions"]
    all_versions = list(versions.keys())

    print(all_versions)


def sha256_file(filename):
    h = hashlib.sha256()
    with open(filename, "rb") as f:
        while chunk := f.read(8192):
            h.update(chunk)
    return h.hexdigest()


def download_big_file(url: str, file_path: Path | str):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req) as response, open(file_path, "wb") as f:
        while chunk := response.read(8192):
            f.write(chunk)


def download_cr_jar(version_id: str, json: dict):
    if version_id == "latest":
        version_id = json["latest"]["alpha"]

    version_json = None
    for version in json["versions"]:
        if version["id"] == version_id:
            version_json = version

    if version_json is None:
        print(f"{RED}Version '{version_id}' not found{RESET}")
        exit(1)

    url = version_json["server"]["url"]
    jar_sha256 = version_json["server"]["sha256"]

    print("Downloading CR jar...")
    download_big_file(url, CR_SERVER_JAR)

    print("Checking sha256...")
    if sha256_file(CR_SERVER_JAR) != jar_sha256:
        print(RED + "sha256 does not match" + RESET)
        exit(1)


# https://repo1.maven.org/maven2/dev/puzzleshq/puzzle-loader-cosmic/1.0.0-alpha/
def make_maven_url(maven_url: str, maven: str) -> str:
    parts: list = maven.split(":")

    if not maven_url.endswith("/"):
        maven_url += "/"

    url = maven_url
    url += parts[0].replace(".", "/")
    url += "/" + parts[1]
    url += "/" + parts[2]

    url += "/" + parts[1] + "-" + parts[2]

    if len(parts) == 4:
        url += "-" + parts[3]

    url += ".jar"

    return url


def maven_artifact_exists(url: str) -> bool:
    req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status == 200
    except urllib.error.HTTPError as e:
        if e.code == 405:
            req = urllib.request.Request(url, method="GET", headers={"User-Agent": "Mozilla/5.0"})
            try:
                with urllib.request.urlopen(req, timeout=10) as resp:
                    resp.read(1)
                    return True
            except Exception:
                return False
        return False
    except urllib.error.URLError:
        return False


def get_url_file_name(url: str) -> str:
    return url.split("/")[-1]


def download_sha(file_url: str) -> str | None:
    try:
        req = urllib.request.Request(file_url + "." + "sha256", headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.read().decode().strip()
    except HTTPError:
        return None


def download_puzzle(type: str, version_id: str, json: dict, refresh: bool = False):
    if version_id == "latest":
        version_id = json["latest"]["*"]

    if version_id in json["versions"]:
        version_json = json["versions"][version_id]
    else:
        print(f"{RED}Version '{version_id}' not found{RESET}")
        exit(1)

    maven = version_json["maven-central"]
    maven += ":common"

    LIBS_DIR.mkdir(parents=True, exist_ok=True)

    url = make_maven_url(MAVEN_CENTRAL_LINK, maven)
    print(f"Downloading Puzzle {type.capitalize()} Common jar...")
    file_path = LIBS_DIR.joinpath(get_url_file_name(url))
    download_big_file(url, file_path)
    sha = download_sha(url)

    print("Checking sha256...")
    if sha256_file(file_path) != sha:
        print(RED + "sha256 does not match" + RESET)
        exit(1)

    url = make_maven_url(MAVEN_CENTRAL_LINK, version_json["maven-central"] + ":server")
    print(f"Downloading Puzzle {type.capitalize()} Server jar...")
    file_path = LIBS_DIR.joinpath(get_url_file_name(url))
    download_big_file(url, file_path)
    sha = download_sha(url)

    print("Checking sha256...")
    if sha256_file(file_path) != sha:
        print(RED + "sha256 does not match" + RESET)
        exit(1)

    lib_json = download_lib_json(version_json["dependencies"], type)

    print("Getting Maven Urls..")
    repos = lib_json["repos"]
    maven_urls = get_maven_urls(repos)

    print("Downloading Common Libs...")
    download_libs(maven_urls, "common", lib_json)

    print("Downloading Server Libs...")
    download_libs(maven_urls, "server", lib_json)


def get_maven_urls(repos: list) -> list:
    urls = []
    for repo in repos:
        urls.append(repo["url"])

    urls = set(urls)
    urls = list(urls)

    try:
        urls.remove(PUZZLE_MAVEN_LINK)
        urls.append(PUZZLE_MAVEN_LINK)
    except ValueError:
        pass

    try:
        urls.remove(JITPACK_LINK)
        urls.append(JITPACK_LINK)
    except ValueError:
        pass

    try:
        urls.remove(MAVEN_CENTRAL_LINK)
        urls.insert(0, MAVEN_CENTRAL_LINK)
        for url in urls:
            if url == MAVEN_CENTRAL_2_LINK:
                urls.remove(MAVEN_CENTRAL_2_LINK)
    except ValueError:
        pass

    return urls


def download_libs(maven_urls, side: str, json: dict):
    json_side = json[side]

    #dev.puzzleshq:puzzle-loader-core:1.4.4-alpha
    for lib in json_side:
        if lib["type"] == "compileOnly": continue

        maven = f"{lib['groupId']}:{lib['artifactId']}:{lib['version']}"
        if "classifier" in lib:
            maven += f":{lib['classifier']}"

        found_url = None
        for maven_url in maven_urls:
            url = make_maven_url(maven_url, maven)

            if maven_artifact_exists(url):
                found_url = url
                break

        if not found_url:
            print(RED + "Couldn't find " + RESET + maven)
            exit(1)

        print("Downloading " + maven)
        file_name = maven.replace(".", "-").replace(":", "-") + ".jar"
        download_big_file(found_url, LIBS_DIR.joinpath(file_name))

        print("Checking sha256...")
        sha = download_sha(found_url)
        if sha is None:
            print(RED + "Couldn't Download Sha " + RESET + maven)
            continue

        if sha256_file(LIBS_DIR.joinpath(file_name)) != sha:
            print(RED + "sha256 does not match" + RESET)
            exit(1)


def parser_args():
    parser = argparse.ArgumentParser(description="Install Puzzle server")

    parser.add_argument("-cr", "--cosmic", help="Cosmic Reach Version", default="latest")
    parser.add_argument("--puzzle-cosmic", help="Puzzle Loader Cosmic Version", default="latest")
    parser.add_argument("--puzzle-core", help="Puzzle Loader Core", default="latest")
    parser.add_argument("-o", "--output", help="Output DIR", default="cosmic_reach_puzzle")
    parser.add_argument("-r", "--refresh", help="Refresh The Downloaded Jsons", action="store_true")
    parser.add_argument("--versions", "-v", help="Print The Versions Available", action="store_true")
    parser.add_argument("--delete", "-d", help="Delete The Output DIR And Installer Files", action="store_true")

    return parser.parse_args()

if __name__ == '__main__':
    args = parser_args()

    if args.versions:
        print_versions()
        exit(0)

    global OUTPUT_DIR, LIBS_DIR, CR_SERVER_JAR
    OUTPUT_DIR = Path(args.output)
    LIBS_DIR = OUTPUT_DIR.joinpath("libs")
    CR_SERVER_JAR = OUTPUT_DIR.joinpath("cosmic-reach-server.jar")

    if args.delete:
        OUTPUT_DIR.rmdir()
        PUZZLE_INSTALLER_DIR.rmdir()

    if not OUTPUT_DIR.exists():
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print("Downloading Puzzle Core Versions JSON...")
    p_core_json = download_repo_json(CORE_REPO, args.refresh)
    print("Downloading Puzzle Core...")
    download_puzzle("core", args.puzzle_cosmic, p_core_json, args.refresh)

    print("Downloading Puzzle Cosmic Versions JSON...")
    p_cosmic_json = download_repo_json(COSMIC_REPO, args.refresh)
    print("Downloading Puzzle Cosmic...")
    download_puzzle("cosmic", args.puzzle_cosmic, p_cosmic_json, args.refresh)

    print("Downloading Cosmic Reach Versions JSON...")
    cr_json = download_CR_version_json(args.refresh)
    print("Downloading Cosmic Reach..")
    download_cr_jar(args.cosmic, cr_json)

    #TODO make a start script and a docker file
