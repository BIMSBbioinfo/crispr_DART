# crispr-DART pipeline
#
# Copyright © 217-2020 Bora Uyar <bora.uyar@mdc-berlin.de>
#
# This file is part of the crispr-DART pipeline
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.


"""
Snakefile for crispr-DART pipeline
"""
import sys
import os
import yaml
import pandas as pd
from itertools import chain


# tools
RSCRIPT = config['tools']['Rscript']

# input locations
SRC_DIR = os.path.abspath(config['source-dir'])
READS_DIR = os.path.abspath(config['reads-dir'])
SAMPLE_SHEET_FILE = os.path.abspath(config['sample_sheet'])
CUT_SITES_FILE = os.path.abspath(config['cutsites'])
COMPARISONS_FILE = os.path.abspath(config.get('comparisonsFile', {}))
REFERENCE_FASTA = os.path.abspath(config['reference_fasta'])

#output locations
OUTPUT_DIR = os.path.abspath(config['output-dir'])
TRIMMED_READS_DIR = os.path.join(OUTPUT_DIR, 'trimmed_reads')
LOG_DIR           = os.path.join(OUTPUT_DIR, 'logs')
FASTA_DIR         = os.path.join(OUTPUT_DIR, 'fasta')
FASTQC_DIR        = os.path.join(OUTPUT_DIR, 'fastqc')
MULTIQC_DIR       = os.path.join(OUTPUT_DIR, 'multiqc')
MAPPED_READS_DIR  = os.path.join(OUTPUT_DIR, 'aln')
INDELS_DIR      = os.path.join(OUTPUT_DIR, 'indels')
BBMAP_INDEX_DIR   = os.path.join(OUTPUT_DIR, 'bbmap_indexes')
REPORT_DIR        = os.path.join(OUTPUT_DIR, 'reports')

#other parameters
nodeN = config['nodeN']

## Load sample sheet
SAMPLE_SHEET = pd.read_csv(SAMPLE_SHEET_FILE)
TARGET_NAMES = list(set(SAMPLE_SHEET['target_name'].tolist()))
# get unique rows for only considering sample id/name/read files
# (one sample may contain multiple target region/name fields, but we
# don't need to process the same read files for each target region)
SAMPLE_SHEET_tmp = SAMPLE_SHEET[['sample_name', 'reads', 'reads2', 'tech']]
SAMPLE_SHEET = SAMPLE_SHEET_tmp.drop_duplicates()

SAMPLES = SAMPLE_SHEET['sample_name'].tolist()

# look up values from sample sheet (assuming it is a data frame) for multiple fields
def lookup(column, predicate, fields=[]):
    values = [SAMPLE_SHEET[SAMPLE_SHEET[column] == predicate][f].tolist() for f in fields]
    values = list(chain.from_iterable(values))
    #remove nan values
    return([f for f in values if str(f) != 'nan'])

def reads_input(wc):
  sample = wc.sample
  files = [os.path.join(READS_DIR, f) for f in lookup('sample_name', sample, ['reads', 'reads2']) if f]
  #print(files)
  return files

def get_bbmap_command(wc):
    sample = wc.sample
    tech = lookup('sample_name', sample, ['tech'])[0]
    if tech == 'illumina':
        return('bbmap.sh')
    elif tech == 'pacbio':
        return('mapPacBio.sh maxlen=6000')

# determine if the sample library is single end or paired end
def libType(wc):
  sample = wc.sample
  files = lookup('sample_name', sample, ['reads', 'reads2'])
  #print(files)
  count = sum(1 for f in files if f)
  if count == 2:
      return 'paired'
  elif count == 1:
      return 'single'

def map_input(wc):
  sample = wc.sample
  if libType(wc) == 'paired':
    return [os.path.join(TRIMMED_READS_DIR, "{sample}_val_1.fq.gz".format(sample=sample)),
            os.path.join(TRIMMED_READS_DIR, "{sample}_val_2.fq.gz".format(sample=sample))]
  elif libType(wc) == 'single':
    return [os.path.join(TRIMMED_READS_DIR, "{sample}_trimmed.fq.gz".format(sample=sample))]


rule all:
    input:
        expand(os.path.join(FASTQC_DIR, "{sample}.fastqc.done"), sample = SAMPLES),
        expand(os.path.join(MAPPED_READS_DIR, "{sample}", "{sample}.bam.bai"), sample = SAMPLES),
        expand(os.path.join(OUTPUT_DIR, "SAMTOOLS", "{sample}.samtools.stats.txt"), sample = SAMPLES),
        os.path.join(OUTPUT_DIR, "multiqc", "multiqc_report.html"),
        expand(os.path.join(INDELS_DIR, "{sample}", "{sample}.sgRNA_efficiency.tsv"), sample = SAMPLES),
        os.path.join(REPORT_DIR, "index.html"),
        expand(os.path.join(REPORT_DIR, "{target}.CoverageProfiles.html"), target = TARGET_NAMES),
        expand(os.path.join(REPORT_DIR, "{target}.SampleComparisons.html"), target = TARGET_NAMES),
        expand(os.path.join(REPORT_DIR, "{target}.sgRNA_efficiency_stats.html"), target = TARGET_NAMES),
        expand(os.path.join(REPORT_DIR, "{target}.Indel_Diversity.html"), target = TARGET_NAMES)

#notice that get_amplicon_file function for 'fasta' should only be used once.
#Other rules that need the amplicon fasta sequence as input should use :
#lambda wildcards: os.path.join(FASTA_DIR, ''.join([wildcards.amplicon, ".fasta"]))
rule reformatFasta:
    input: REFERENCE_FASTA
    output: os.path.join(FASTA_DIR, os.path.basename(REFERENCE_FASTA))
    log: os.path.join(LOG_DIR, ".".join(["reformatFasta", os.path.basename(REFERENCE_FASTA), "log"]))
    params:
        memory = config['tools']['reformat']['memory']
    shell:
        "reformat.sh {params.memory} in={input} out={output} tuc > {log} 2>&1"

rule getFastaIndex:
    input: os.path.join(FASTA_DIR, os.path.basename(REFERENCE_FASTA))
    output: os.path.join(FASTA_DIR, ".".join([os.path.basename(REFERENCE_FASTA), 'fai']))
    log: os.path.join(LOG_DIR, ".".join(["getFastaIndex", os.path.basename(REFERENCE_FASTA), "log"]))
    shell:
        "samtools faidx {input} > {log} 2>&1"

rule getFastaDict:
    input: os.path.join(FASTA_DIR, os.path.basename(REFERENCE_FASTA))
    output: os.path.join(FASTA_DIR, ".".join([os.path.basename(REFERENCE_FASTA).replace(".fa", ""), 'dict']))
    params:
        script=os.path.join(SRC_DIR, "src", "getFastaDict.R")
    log: os.path.join(LOG_DIR, ".".join(["getFastaDict", os.path.basename(REFERENCE_FASTA), "log"]))
    shell:
        "{RSCRIPT} {params.script} {input} {output} > {log} 2>&1"

rule fastqc:
    input: reads_input
    output: os.path.join(FASTQC_DIR, "{sample}.fastqc.done")
    log: os.path.join(LOG_DIR, "FASTQC", "{sample}.fastqc.log")
    shell: "fastqc -o {FASTQC_DIR} {input} > {log} 2>&1; touch {output}"

rule trim_galore_pe:
  input: reads_input
  output:
    r1=os.path.join(TRIMMED_READS_DIR, "{sample}_val_1.fq.gz"),
    r2=os.path.join(TRIMMED_READS_DIR, "{sample}_val_2.fq.gz")
  log: os.path.join(LOG_DIR, "TRIM", "trimgalore.{sample}.log")
  shell: "trim_galore -o {TRIMMED_READS_DIR} --cores 2 --basename {wildcards.sample} --paired {input[0]} {input[1]} >> {log} 2>&1"

rule trim_galore_se:
  input: reads_input
  output: os.path.join(TRIMMED_READS_DIR, "{sample}_trimmed.fq.gz"),
  log: os.path.join(LOG_DIR, "TRIM", "trimgalore.{sample}.log")
  params:
    tech = lambda wildcards: lookup('sample_name', wildcards[0], ['tech'])[0]
  run:
    if params.tech == 'illumina':
        shell("trim_galore -o {TRIMMED_READS_DIR} --cores 2 --basename {wildcards.sample} {input[0]} >> {log} 2>&1")
    elif params.tech == 'pacbio':
        shell("cp {input} {output}")

rule bbmap_indexgenome:
    input: os.path.join(FASTA_DIR, os.path.basename(REFERENCE_FASTA))
    output: directory(os.path.join(BBMAP_INDEX_DIR, re.sub("\.fa(sta)?$", "", os.path.basename(REFERENCE_FASTA))))
    log: os.path.join(LOG_DIR, ".".join(["bbmap_index", os.path.basename(REFERENCE_FASTA), "log"]))
    shell: "bbmap.sh t=10 ref={input} path={output} > {log} 2>&1"

rule bbmap_map:
    input:
        reads = map_input,
        ref = os.path.join(BBMAP_INDEX_DIR, re.sub("\.fa(sta)?$", "", os.path.basename(REFERENCE_FASTA)))
    output:
        os.path.join(MAPPED_READS_DIR, "{sample}", "{sample}.sam")
    params:
        aligner = lambda wildcards: get_bbmap_command(wildcards),
        memory = config['tools']['bbmap']['memory'],
        options = config['tools']['bbmap']['options'],
        libtype = lambda wildcards: libType(wildcards)
    log: os.path.join(LOG_DIR, "BBMAP", "bbmap_align.{sample}.log")
    run:
        if params.libtype == 'single':
            shell("{params.aligner} {params.memory} {params.options} path={input.ref} in={input.reads} outm={output} > {log} 2>&1")
        elif params.libtype == 'paired':
            shell("{params.aligner} {params.memory} {params.options} keepnames=t path={input.ref} in1={input.reads[0]} in2={input.reads[1]} outm={output}> {log} 2>&1")


rule samtools_sam2bam:
    input: os.path.join(MAPPED_READS_DIR,  "{sample}", "{sample}.sam") #os.path.join(MAPPED_READS_DIR,  "{sample}", "{sample}.sam_withreadgroups")
    output: os.path.join(MAPPED_READS_DIR,  "{sample}", "{sample}.bam")
    log: os.path.join(LOG_DIR, "SAMTOOLS", "samtools_sam2bam.{sample}.log")
    shell:
        """
        samtools view -bh {input} | samtools sort -o {output} > {log} 2>&1
        rm {input}
        """

rule samtools_indexbam:
    input: os.path.join(MAPPED_READS_DIR,  "{sample}", "{sample}.bam")
    output: os.path.join(MAPPED_READS_DIR,  "{sample}", "{sample}.bam.bai")
    log: os.path.join(LOG_DIR, "samtools_indexbam.{sample}.log")
    shell: "samtools index {input} > {log} 2>&1"


rule samtools_stats:
    input:
        #bamfile = os.path.join(OUTPUT_DIR, "aln_merged", "{sample}.bam"),
        bamfile=os.path.join(MAPPED_READS_DIR,  "{sample}", "{sample}.bam"),
        ref = os.path.join(FASTA_DIR, os.path.basename(REFERENCE_FASTA))
    output: os.path.join(OUTPUT_DIR, "SAMTOOLS", "{sample}.samtools.stats.txt")
    log: os.path.join(LOG_DIR, "SAMTOOLS", "samtools_stats.{sample}.log")
    shell: "samtools stats --reference {input.ref} {input.bamfile} > {output} 2> {log} 2>&1"

rule multiqc:
    input:
        fastqc = expand(os.path.join(FASTQC_DIR, "{sample}.fastqc.done"), sample = SAMPLES),
        samtools = expand(os.path.join(OUTPUT_DIR, "SAMTOOLS", "{sample}.samtools.stats.txt"), sample = SAMPLES)
    output:
        os.path.join(OUTPUT_DIR, "multiqc", "multiqc_report.html")
    params:
        analysis_folder = OUTPUT_DIR,
        output_folder = os.path.join(OUTPUT_DIR, "multiqc")
    log: os.path.join(LOG_DIR, 'multiqc.log')
    shell: "multiqc --force -o {params.output_folder} {params.analysis_folder} > {log} 2>&1"

rule getIndelStats:
    input:
        bamIndex = os.path.join(MAPPED_READS_DIR, "{sample}", "{sample}.bam.bai"),
        bamFile = os.path.join(MAPPED_READS_DIR, "{sample}", "{sample}.bam")
    output:
        # os.path.join(INDELS_DIR, "{sample}", "{sample}.indelScores.bigwig"),
        # os.path.join(INDELS_DIR, "{sample}", "{sample}.deletionScores.bigwig"),
        # os.path.join(INDELS_DIR, "{sample}", "{sample}.insertionScores.bigwig"),
        # os.path.join(INDELS_DIR, "{sample}", "{sample}.alnCoverage.bigwig"),
        # os.path.join(INDELS_DIR, "{sample}", "{sample}.deletions.bed"),
        # os.path.join(INDELS_DIR, "{sample}", "{sample}.insertions.bed"),
        # os.path.join(INDELS_DIR, "{sample}", "{sample}.indels.tsv"),
        # os.path.join(INDELS_DIR, "{sample}", "{sample}.reads_with_indels.tsv"),
        # os.path.join(INDELS_DIR, "{sample}", "{sample}.insertedSequences.tsv"),
        os.path.join(INDELS_DIR, "{sample}", "{sample}.sgRNA_efficiency.tsv")
    params:
        script = os.path.join(SRC_DIR, "src", "getIndelStats.R"),
        tech = lambda wildcards: lookup('sample_name', wildcards.sample, ['tech'])[0]
    log: os.path.join(LOG_DIR, "indel_stats", "getIndelStats.{sample}.log")
    shell: "{RSCRIPT} {params.script} {input.bamFile} {wildcards.sample} {INDELS_DIR} {CUT_SITES_FILE} {params.tech} > {log} 2>&1"

#prepare _site.yml and other Rmd files to be rendered into a html report (see renderSite rule)
rule generateSiteFiles:
    input: 
        expand(os.path.join(INDELS_DIR, "{sample}", "{sample}.sgRNA_efficiency.tsv"), sample = SAMPLES)
    output:
        os.path.join(REPORT_DIR, "_site.yml"),
        os.path.join(REPORT_DIR, "index.Rmd"),
        os.path.join(REPORT_DIR, "config.yml"),
        expand(os.path.join(REPORT_DIR, "{target}.CoverageProfiles.Rmd"), target = TARGET_NAMES),
        expand(os.path.join(REPORT_DIR, "{target}.SampleComparisons.Rmd"), target = TARGET_NAMES),
        expand(os.path.join(REPORT_DIR, "{target}.sgRNA_efficiency_stats.Rmd"), target = TARGET_NAMES),
        expand(os.path.join(REPORT_DIR, "{target}.Indel_Diversity.Rmd"), target = TARGET_NAMES)
    params:
        report_scripts_dir = os.path.join(SRC_DIR, "src", "report_scripts"),
        script = os.path.join(SRC_DIR, "src", "generateSiteFiles.R")
    log: os.path.join(LOG_DIR, "generateSiteFiles.log")
    shell:
        "{RSCRIPT} {params.script} {params.report_scripts_dir} {SAMPLE_SHEET_FILE} {CUT_SITES_FILE} {COMPARISONS_FILE} {OUTPUT_DIR} {REPORT_DIR} {RSCRIPT} > {log} 2>&1"

rule renderReport_coverage:
    input:
        os.path.join(REPORT_DIR, "{target}.CoverageProfiles.Rmd")
    output:
        os.path.join(REPORT_DIR, "{target}.CoverageProfiles.html")
    log: os.path.join(LOG_DIR, "renderReports", "{target}.coverage_profile.log")
    shell:
        "{RSCRIPT} -e \"library(rmarkdown); rmarkdown::render_site(\'{input[0]}\')\" > {log} 2>&1"

rule renderReport_indeldiversity:
    input:
        os.path.join(REPORT_DIR, "{target}.Indel_Diversity.Rmd")
    output:
        os.path.join(REPORT_DIR, "{target}.Indel_Diversity.html")
    log: os.path.join(LOG_DIR, "renderReports", "{target}.indel_diversity.log")
    shell:
        "{RSCRIPT} -e \"library(rmarkdown); rmarkdown::render_site(\'{input[0]}\')\" > {log} 2>&1"

rule renderReport_sgRNA:
    input:
        os.path.join(REPORT_DIR, "{target}.sgRNA_efficiency_stats.Rmd")
    output:
        os.path.join(REPORT_DIR, "{target}.sgRNA_efficiency_stats.html")
    log: os.path.join(LOG_DIR, "renderReports", "{target}.sgRNA_efficiency_stats.log")
    shell:
        "{RSCRIPT} -e \"library(rmarkdown); rmarkdown::render_site(\'{input[0]}\')\" > {log} 2>&1"

rule renderReport_comparison:
    input:
        os.path.join(REPORT_DIR, "{target}.SampleComparisons.Rmd")
    output:
        os.path.join(REPORT_DIR, "{target}.SampleComparisons.html")
    log: os.path.join(LOG_DIR, "renderReports", "{target}.comparison.log")
    shell:
        "{RSCRIPT} -e \"library(rmarkdown); rmarkdown::render_site(\'{input[0]}\')\" > {log} 2>&1"

rule renderSite:
    input:
        os.path.join(REPORT_DIR, "_site.yml"),
        os.path.join(REPORT_DIR, "index.Rmd"),
        os.path.join(REPORT_DIR, "config.yml"),
        expand(os.path.join(REPORT_DIR, "{target}.CoverageProfiles.html"), target = TARGET_NAMES),
        expand(os.path.join(REPORT_DIR, "{target}.SampleComparisons.html"), target = TARGET_NAMES),
        expand(os.path.join(REPORT_DIR, "{target}.sgRNA_efficiency_stats.html"), target = TARGET_NAMES),
        expand(os.path.join(REPORT_DIR, "{target}.Indel_Diversity.html"), target = TARGET_NAMES)
    output:
        os.path.join(REPORT_DIR, "index.html")
    params:
        report_scripts_dir = os.path.join(SRC_DIR, "src", "report_scripts")
    log: os.path.join(LOG_DIR, "renderSite.log")
    shell:
        "{RSCRIPT} -e \"library(rmarkdown); rmarkdown::render_site(\'{input[1]}\')\" > {log} 2>&1"
