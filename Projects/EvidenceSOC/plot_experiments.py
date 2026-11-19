"""Render the two stage 7 figures from the recorded measurements (optional matplotlib)."""
import argparse
import json
from pathlib import Path
from statistics import median
from zipfile import ZipFile

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt


def plot(archive_path, output):
    with ZipFile(archive_path) as archive:
        metrics = json.loads(archive.read("detectors.json"))[0]["metrics"]
        runtime = json.loads(archive.read("runtime.json"))["rows"]
    fig, (ax, clock) = plt.subplots(1, 2, figsize=(11, 4.2), layout="constrained")
    names = ("Rules", "Isolation Forest", "Combined")
    for i, (name, color) in enumerate(zip(names, ("#345644", "#639285", "#a66939"), strict=True)):
        ax.bar([v + (i - 1) * .25 for v in range(3)], [100 * metrics[name][k] for k in ("precision","recall","f1")],
               width=.23, color=color, label=name)
    ax.set(xticks=range(3), xticklabels=("Precision", "Recall", "F1"), ylabel="Score (%)",
           ylim=(0, 101), title="Detection on held-out seed 42")
    ax.legend(loc="upper left", fontsize=8, ncols=3)
    for i, (phase, device) in enumerate([("warm", "gpu"), ("warm", "cpu"), ("cold", "gpu"), ("cold", "cpu")]):
        times = [r["wall_seconds"] for r in runtime if r["phase"] == phase and r["device"] == device]
        color = "#345644" if device == "gpu" else "#a66939"
        clock.hlines(i, min(times), max(times), color=color, linewidth=2)
        clock.scatter(times, [i]*len(times), facecolors="none", edgecolors=color, s=38)
        clock.scatter(median(times), i, marker="D", s=38, color=color)
    clock.set(yticks=range(4), yticklabels=("GPU warm", "CPU warm", "GPU cold", "CPU cold"),
              xlabel="Chat request, seconds (log scale)", title="Local Llama latency")
    clock.set_xscale("log")
    clock.set_ylim(3.6, -.6)
    clock.set_xticks([.5,1,2,5,10,20,50], labels=["0.5","1","2","5","10","20","50"])
    for axis in (ax, clock):
        axis.spines[["right","top"]].set_visible(False)
        axis.set_axisbelow(True)
    ax.grid(axis="y", alpha=.18)
    clock.grid(axis="x", alpha=.18)
    fig.savefig(output, dpi=170)
    plt.close(fig)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    plot(args.archive, args.output)
