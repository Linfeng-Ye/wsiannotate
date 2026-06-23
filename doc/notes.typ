#import "@preview/lasaveur:0.1.4": *
#import "@preview/cetz:0.3.4"

#set document(title: "Manual for IQA Subjective Test")

// #set page(paper: "us-letter", fill: blue.lighten(90%))  //  On-screen
#set page(paper: "us-letter")                           //  Printed

#set math.equation(numbering: "(1)")
#set math.mat(delim: "[")

#let show_plots = true     // Set this to false if `history` is not presented

#let ques(body) = [#highlight(fill: orange.lighten(30%))[*Question*: #body]]
#let prob(body) = [#highlight(fill: lime.mix((aqua, 30%)).lighten(30%))[*Problem*: #body]]
#let prob2(body) = [#highlight(fill: lime.mix((yellow, 30%)).lighten(30%))[*Problem*: #body]]
#let expl(body) = [#highlight(fill: green.lighten(30%))[*Explanation*: #body]]
#let hl(body) = [#highlight(fill: red.lighten(50%))[#body]]
#let hl2(body) = [#highlight(fill: yellow.lighten(50%))[#body]]
#let hl3(body) = [#highlight(fill: green.lighten(50%))[#body]]
#let hl4(body) = [#highlight(fill: blue.lighten(50%))[#body]]
#let hlf(body) = [#text(style: "italic", fill: red)[#body]]
#let TODO(body) = [#highlight(fill: yellow.lighten(60%))[#text(style: "italic", fill: red.darken(10%))[*TODO*: #body]]]
#let DOING(body) = [#highlight(fill: blue.lighten(60%))[#text(style: "italic", fill: red.darken(10%))[*DOING*: #body]]]

#let disabled(body) = [#strike[#text(style: "italic", fill: gray)[#body]]]

#let hlt(color: red, body) = {
  // highlight(extend: (y: 10pt), fill: color.transparentize(50%), body)
  text(weight: 800, fill: color, body)
}
#let hlt1(body) = {
  hlt(color: red, body)
}
#let hlt2(body) = {
  hlt(color: yellow.darken(50%), body)
}
#let hlt3(body) = {
  hlt(color: lime.darken(30%), body)
}
#let hlt4(body) = {
  hlt(color: blue, body)
}
#let hlt5(body) = {
  hlt(color: red.mix((yellow, 30%)), body)
}

#let hltt(color: red, body) = {
  // highltight(extend: (y: 10pt), fill: color.transparentize(50%), body)
  text(weight: 600, fill: color, body)
}
#let hltt1(body) = {
  text(weight: 600, fill: red, body)
}
#let hltt2(body) = {
  hltt(color: yellow.darken(50%).at(3), body)
}
#let hltt3(body) = {
  hltt(color: lime.darken(30%), body)
}
#let hltt4(body) = {
  hltt(color: blue, body)
}
#let hltt5(body) = {
  hltt(color: red.mix((yellow, 30%)), body)
}


#let loss(body) = [#text(fill: red, style: "italic", underline(body))]
// #let var(body) = [#text(fill: blue, underline(body))]
#let var(body) = [#text(fill: blue, style: "italic", body)]
#let met(body) = [#text(fill: green.darken(30%), style: "italic", body)]
#let mod(body) = [#text(fill: orange, weight: "bold", body)]
#let obj(body) = [#text(fill: yellow.mix(orange), body)]
#let typ(body) = [#text(fill: green, weight: "bold", style: "italic", body)]
#let note(body) = [#text(fill: gray, body)]
#let toggle(body) = [#text(fill: blue, style: "italic")[⏼ #body]]
#let config(body) = [#text(fill: red.darken(30%), body)]
#let fname(body) = [#text(fill: purple, style: "italic", body)]
#let experiment(body) = [#text(fill: red, weight: "bold", body)]
#let exp-name(body) = [#highlight(fill: blue.lighten(80%))[#text(fill: purple, style: "italic")[*Experiment* #body]]]
#let todo = box(fill: yellow.mix((green, 30%)).lighten(40%), stroke: black, inset: 2pt, baseline: 30%)[#sym.circle TODO] 
#let todonext = box(fill: yellow.mix((green, 80%)).lighten(40%), stroke: black, inset: 2pt, baseline: 30%)[#sym.circle Next Thing TODO] 
#let unknown = box(fill: gray.lighten(40%), stroke: black, inset: 2pt, baseline: 30%)[? Unknown] 
#let done = box(fill: green.lighten(40%), stroke: black, inset: 2pt, baseline: 30%)[#sym.checkmark Done] 
#let ptdone = box(fill: yellow.lighten(40%), stroke: black, inset: 2pt, baseline: 30%)[#sym.checkmark partially done]
#let attempted = box(fill: aqua.lighten(40%), stroke: black, inset: 2pt, baseline: 30%)[#sym.circle attempted]
#let attempting = box(fill: red.mix(blue).lighten(40%), stroke: black, inset: 2pt, baseline: 30%)[... attempting]
#let pend = box(fill: orange.lighten(40%), stroke: black, inset: 2pt, baseline: 30%)[? Pending indefinitely]
#let added = box(fill: orange.lighten(40%), stroke: black, inset: 2pt, baseline: 30%)[#sym.plus Added]
#let failed = box(fill: red.lighten(40%), stroke: black, inset: 2pt, baseline: 30%)[#sym.times Failed]
#let modified = box(fill: orange.mix(yellow).lighten(40%), stroke: black, inset: 2pt, baseline: 30%)[\* Modified]

#let card(body, color: blue, head: "Note") = {
  block(
    fill: color.lighten(80%),
    inset: 5pt,
    radius: 4pt, 
    width: 100%,
  )[
    #text(fill: color.darken(50%))[#if head != "" [*#head*: ]]
    #body
  ]
}
#let info_card(body) = card(body, color: yellow.mix((green, 40%)), head: "")
#let issue_card(body) = card(body, color: orange.mix((yellow, 40%)), head: "Issues")
#let cfg_card(body) = card(body, color: yellow.mix((orange, 30%)), head: "Configuration")
#let exp_info_card(head: "", body) = {
  // Newer info card that facilitates table view. 
  let head = if head == "" { "Experiment Information" } else { "Experiment Information (" + head + ")" }
  card(body, color: rgb("#ccFF39"), head: head)
}
#let id_card(head: "", body) = {
  let head = if head == "" { "ID" } else { "ID (" + head + ")" }
  card(body, color: red.mix((orange, 30%)), head: head)
}
#let proof_card(body) = text(size: 10pt, card(body, color: aqua.mix((green, 30%)), head: "Proof"))
#let result_card(body, ok: false, waiting: false, resolved: false, head: "") = {
  let head = if head == "" { "Result" } else { "Result (" + head + ")" }
  if resolved and waiting {
    card(body, color: black.mix((blue, 30%), space: color.rgb), head: head)
  } else if resolved {
    card(body, color: black.mix((red, 10%), space: color.rgb), head: head)
  } else if ok {
    card(body, color: green.mix((aqua, 10%), space: color.rgb), head: head)
  } else if waiting {
    card(body, color: blue.mix((aqua, 30%), space: color.rgb), head: head)
  } else {
    card(body, color: red.mix((aqua, 30%), space: color.rgb), head: head)
  }
}
#let bug_card(body) = text(size: 10pt, card(body, color: orange.darken(50%), head: "Smelly bug"))
#let command_card(body) = text(size: 8pt, card(body, color: gray.lighten(50%), head: "Command"))

#let small(body) = text(size: 8pt, body)
#let tiny(body) = text(size: 6pt, body)

#let info_table_fill = (x, y) => {
  if x == 0 {
    red.lighten(60%)
  } else {
    none
  }
}
#let tba = table.cell(fill: luma(80%))[Baseline]
#let tok = table.cell(fill: green.lighten(60%))[OK]
#let tin = table.cell(fill: orange.mix(green, space: rgb).lighten(60%))[Intersting]
#let tpo = table.cell(fill: orange.lighten(60%))[Partially OK]
#let tpob(body) = table.cell(fill: orange.lighten(60%))[Partially OK: #body]
#let tfa = table.cell(fill: red.lighten(60%))[fail]
#let tfab(body) = table.cell(fill: red.lighten(60%))[fail: #body]
#let ton = table.cell(fill: aqua.lighten(60%))[ongoing]
#let twa = table.cell(fill: aqua.desaturate(70%).lighten(50%))[waiting]
#let tca = table.cell(fill: black.lighten(80%))[cancelled]

#let exp_tag(body) = box(fill: yellow.mix((green, 30%)).lighten(40%), stroke: black, inset: 2pt, baseline: 30%)[#text(fill: red, weight: "bold")[*Tag*: #body]]

// Toggle this if images not in the git repo are not available.
#let SHOW_UNGIT_IMAGE = true 

#let ungit-image(fname, width: auto) = if SHOW_UNGIT_IMAGE {
  image(fname, width: width)
} else {
  box(fill: gray.lighten(50%), stroke: black, inset: 5pt, width: 90%, height: 100pt)[#text(fill: red)[Ungit image: #body]]
}

#align(center)[#text(size: 30pt)[*Manual for IQA Subjective Test*]]

#text(size: 20pt, fill: red)[For internal reference only.  Do not distribute.]


#outline(depth: 3)


#set heading(numbering: "1.1 ")
#show heading: it => [
  // #set text(font: "Inria Serif")
  #set text(fill: blue.darken(100% / (it.level + 1)))
  #if it.level == 1 [
    #align(center)[ 
      #counter(heading).display(it.numbering)
      #it.body 
    ]
  ] else [
    #counter(heading).display(it.numbering)
    #it.body
  ]
]
#show figure.caption: it => [
  #align(center)[
    #text(size: 10pt, fill: gray.darken(60%))[#it]
  ]
]
#let legend(body) = [
  #text(size: 10pt, fill: gray.darken(60%))[#body]
]
#set math.equation(numbering: "(1)")
#set par(justify: true)
#show link: set text(fill: blue)
#show ref: set text(fill: blue.darken(30%))
#show cite: set text(fill: green)


= Overview

This tool is a Django-based web application for conducting *Image Quality Assessment (IQA) subjective tests*.  It supports two evaluation modes:

+ *MOS (Mean Opinion Score)* --- A single test image is shown (with an optional reference image displayed alongside).  The subject rates the image quality on a configurable integer scale (default 1--5).

+ *2AFC (Two-Alternative Forced Choice)* --- A pair of test images is shown side by side (each with an optional reference image).  The subject selects which image has better quality.

The system handles user authentication, stimulus sampling, progress tracking, response storage, and CSV export.  All configuration is done through the Django admin interface or via a JSON import command.


#pagebreak(weak: true)


= Code Structure

The project lives in the #fname(`iqa_subjective_test/`) directory.

```
iqa_subjective_test/
├── manage.py                       Django entry point
├── requirements.txt                Python dependencies
├── images/                         Image storage directory (MEDIA_ROOT-relative)
│   └── .gitkeep
│
├── iqa_site/                       Django project package
│   ├── __init__.py
│   ├── settings.py                 Project settings (DB, media, auth URLs)
│   ├── urls.py                     Root URL conf (admin + iqa app)
│   ├── wsgi.py
│   └── asgi.py
│
└── iqa/                            Main application
    ├── __init__.py
    ├── apps.py                     App configuration
    ├── models.py                   Data models (6 models)
    ├── views.py                    View functions (11 views)
    ├── urls.py                     URL patterns (app_name = 'iqa')
    ├── admin.py                    Admin registrations + inlines
    ├── forms.py                    Bulk user creation form
    ├── samplers.py                 Stimulus sampling strategies
    │
    ├── templatetags/
    │   ├── __init__.py
    │   └── iqa_extras.py           Template filter: get_item
    │
    ├── management/
    │   └── commands/
    │       ├── import_study.py     JSON study import command
    │       └── export_responses.py CSV response export command
    │
    ├── migrations/                 Django migrations (auto-generated)
    │
    ├── static/iqa/
    │   ├── css/
    │   │   └── evaluation.css      Evaluation page styles
    │   └── js/
    │       └── zoom.js             Hover-to-zoom overlay logic
    │
    └── templates/
        ├── base.html               Base template (shared layout)
        └── iqa/
            ├── login.html              Login page
            ├── home.html               Study listing / dashboard
            ├── mos_evaluation.html      MOS rating interface
            ├── pair_evaluation.html     2AFC choice interface
            ├── next_stimulus_redirect.html  Auto-redirect after submit
            ├── study_done.html         Completion message
            ├── view_responses.html     Staff response viewer
            ├── bulk_create_users.html  Bulk user creation form
            └── user_creation_results.html  Created credentials display
```

== Data Models

#table(
  columns: (1fr, 3fr),
  inset: 6pt,
  fill: info_table_fill,
  [*Model*], [*Purpose*],
  [`Image`], [Stores an image file (#fname(`images/`) upload directory) and an optional display name.],
  [`Study`], [Top-level configuration: name, mode (`MOS` or `2AFC`), prompt text, scale range and labels (MOS only), sampling strategy, and active flag.],
  [`MOSStimulus`], [Links a test `image` to a Study, with an optional `reference` image.  Has an `order` field for presentation sequencing.],
  [`PairStimulus`], [Links `image_a` and `image_b` to a Study, each with optional `reference_a` / `reference_b`.  Has an `order` field.],
  [`MOSResponse`], [Stores a subject's integer `score` for a MOS stimulus.  Unique per (stimulus, user) pair.],
  [`PairResponse`], [Stores a subject's `choice` (`A` or `B`) for a pair stimulus.  Unique per (stimulus, user) pair.],
)

== Sampling Strategies

The #fname(`samplers.py`) module provides three strategies, selected per-study via the `sampler` field:

- *`sequential`* --- Presents stimuli in ascending `(order, id)`.  Deterministic ordering.
- *`random`* --- Picks a random unevaluated stimulus each time.
- *`least_evaluated`* --- Picks the stimulus with the fewest total responses across all users, breaking ties by `(order, id)`.  Useful for balancing response counts when subjects may not complete all stimuli.


#pagebreak(weak: true)


= Command-Line Reference

All commands are run from inside the #fname(`iqa_subjective_test/`) directory.

== `manage.py` --- Django Management

=== Initial Setup

```bash
# Create database tables
python manage.py makemigrations iqa
python manage.py migrate

# Create an administrator account
python manage.py createsuperuser

# Start the development server
python manage.py runserver [port]
```

The default port is `8000`.  The application is then accessible at:
- Subject interface: `http://localhost:8000/iqa/`
- Admin interface: `http://localhost:8000/admin/`

=== `import_study` --- Import or Append Stimuli

*Synopsis:*

#command_card[```
python manage.py import_study [--activate] [--append-to STUDY_ID] <json_file>
```]

*Description:*

Reads a JSON file describing a study and its stimuli, creates the corresponding `Study`, `Image`, and stimulus objects in the database.  Image paths in the JSON are relative to #config(`MEDIA_ROOT`) (which defaults to the #fname(`iqa_subjective_test/`) directory).

When `--append-to` is given, no new study is created.  Instead, the `stimuli` list from the JSON is appended to the existing study identified by `STUDY_ID`.  The new stimuli are assigned `order` values starting after the highest existing order in that study.  All other fields in the JSON (`name`, `prompt`, `scale_*`, `sampler`) are ignored in append mode.  If the JSON contains a `mode` field, it must match the existing study's mode.

*Options:*

#table(
  columns: (1.5fr, 3fr),
  inset: 6pt,
  [`json_file`], [Path to the JSON file to import (required positional argument).],
  [`--activate`], [If given, the study is marked `is_active=True` immediately so subjects can see it.  Ignored when appending.],
  [`--append-to STUDY_ID`], [Append the stimuli from the JSON file to an existing study (specified by its numeric ID) instead of creating a new one.],
)

*JSON format for MOS:*

```json
{
    "name": "My MOS Study",
    "mode": "MOS",
    "prompt": "Rate the quality of the image.",
    "scale_min": 1,
    "scale_max": 5,
    "scale_min_label": "Bad",
    "scale_max_label": "Excellent",
    "sampler": "sequential",
    "image_sizing": "scaled",
    "image_scale_factor": 0.5,
    "zoom_enabled": true,
    "zoom_factor": 3.0,
    "stimuli": [
        {
            "image": "images/distorted_001.png",
            "reference": "images/reference_001.png"
        },
        {
            "image": "images/distorted_002.png"
        }
    ]
}
```

Each stimulus entry has a required `image` key and an optional `reference` key.  The `scale_*`, `sampler`, `image_sizing`, `image_scale_factor`, `zoom_enabled`, and `zoom_factor` fields are optional and default to a 1--5 scale, sequential sampling, fit-to-screen sizing, and zoom disabled.

*JSON format for 2AFC:*

```json
{
    "name": "My 2AFC Study",
    "mode": "2AFC",
    "prompt": "Which image has better quality?",
    "sampler": "random",
    "stimuli": [
        {
            "image_a": "images/method_a_001.png",
            "image_b": "images/method_b_001.png",
            "reference_a": "images/ref_001.png",
            "reference_b": "images/ref_001.png"
        },
        {
            "image_a": "images/method_a_002.png",
            "image_b": "images/method_b_002.png"
        }
    ]
}
```

Each stimulus entry requires `image_a` and `image_b`.  The `reference_a` and `reference_b` fields are optional and independent---you can provide a reference for one image but not the other, or the same reference for both.

*Examples:*

Create a new study and activate it:
#command_card[```
python manage.py import_study studies/blur_mos.json --activate
```]

Append additional stimuli to study with id=3:
#command_card[```
python manage.py import_study extra_images.json --append-to 3
```]

=== `export_responses` --- Export Responses to CSV <export-cmd>

*Synopsis:*

#command_card[```
python manage.py export_responses [-s ID_OR_NAME] [-o FILE]
```]

*Description:*

Exports subjective-test responses to CSV.  By default all studies are included (they must share the same mode); use `--study` to restrict to a single study.  Output goes to stdout unless `--output` is given.

For MOS studies the CSV columns are:

#table(
  columns: (1fr, 1fr, 1fr, 1fr, 1fr, 1fr, 1fr),
  inset: 5pt,
  [`study`], [`stimulus_order`], [`image`], [`reference`], [`user`], [`score`], [`timestamp`],
)

For 2AFC studies the CSV columns are:

#table(
  columns: (1fr, 1fr, 1fr, 1fr, 1fr, 1fr, 1fr, 1fr, 1fr),
  inset: 5pt,
  [`study`], [`stimulus_order`], [`image_a`], [`image_b`], [`reference_a`], [`reference_b`], [`user`], [`choice`], [`timestamp`],
)

*Options:*

#table(
  columns: (1.5fr, 3fr),
  inset: 6pt,
  [`-s`, `--study ID_OR_NAME`], [Export only the specified study.  Accepts a numeric ID or the exact study name.],
  [`-o`, `--output FILE`], [Write CSV to FILE instead of stdout.],
)

*Examples:*

Export a single study by ID to a file:
#command_card[```bash
python manage.py export_responses --study 3 -o results.csv
```]

Export a study by name, piping to another tool:
#command_card[```bash
python manage.py export_responses -s "Blur MOS" | head
```]

Export all studies (stdout):
#command_card[```bash
python manage.py export_responses
```]


== `scripts/generate_dev_test.py` --- Generate Dev Test Dataset

*Synopsis:*

#command_card[```
python scripts/generate_dev_test.py [options] <live_dir>
```]

*Description:*

Generates a development test image set from the LIVE IQA dataset.  The script randomly samples distorted images from a CSV file list, center-crops each distorted image and its corresponding reference to 512$times$512 pixels, saves them as PNG files under the output directory, and produces a JSON file ready for `import_study`.

Two modes are supported:
- *MOS* (default): each stimulus is a single distorted image with its reference.
- *2AFC*: stimuli are pairs of distorted images.  By default all pairs share the same reference scene.  The `--cross-ref FRAC` option controls the fraction of pairs drawn from _different_ reference scenes (each side gets its own reference image).  For example, `--cross-ref 0.3` produces 70% same-scene pairs and 30% cross-scene pairs.

The LIVE dataset root directory must contain the standard subdirectory layout:

```
<live_dir>/
├── refimgs/          reference BMPs
├── jp2k/             JPEG 2000 distortions
├── jpeg/             JPEG distortions
├── wn/               white noise
├── gblur/            Gaussian blur
└── fastfading/       fast-fading (Rayleigh) distortions
```

*Positional argument:*

#table(
  columns: (1.5fr, 3fr),
  inset: 6pt,
  [`live_dir`], [Root directory of the LIVE dataset (must contain a #fname(`refimgs/`) subdirectory).],
)

*Options:*

#table(
  columns: (1.5fr, 3fr),
  inset: 6pt,
  [`--mode {MOS,2AFC}`], [Study mode.  Default: `MOS`.],
  [`--cross-ref FRAC`], [2AFC only.  Fraction (0.0--1.0) of pairs drawn from different reference scenes.  Default `0.0` (all same-scene).  Setting `1.0` makes all pairs cross-scene.],
  [`--csv PATH`], [Path to the filelist CSV.  Default: #fname(`tmp/filelist.csv`).],
  [`--outdir PATH`], [Output directory for cropped PNG images.  Default: #fname(`images/live_dev/`).],
  [`--json PATH`], [Output path for the generated study JSON.  Default: #fname(`scripts/live_dev_mos.json`) for MOS, #fname(`scripts/live_dev_2afc.json`) for 2AFC.],
  [`-n N`], [Number of stimuli to sample (individual images for MOS, pairs for 2AFC).  Default: `50`.],
  [`--seed SEED`], [Random seed for reproducible sampling.  Default: `42`.],
)

*Outputs:*

- Cropped 512$times$512 PNG images in #fname(`<outdir>/<distortion_type>/`) and #fname(`<outdir>/refimgs/`).
- A study JSON file at #fname(`<json>`) with paths relative to #config(`MEDIA_ROOT`).

*Example workflow (MOS):*

#command_card[```bash
# 1.  Generate the dev test images and JSON
python scripts/generate_dev_test.py /data/LIVE

# 2.  Import the generated study
python manage.py import_study scripts/live_dev_mos.json --activate

# 3.  Start the server and evaluate
python manage.py runserver
```]

*Example workflow (2AFC, all same-scene):*

#command_card[```bash
python scripts/generate_dev_test.py /data/LIVE --mode 2AFC
python manage.py import_study scripts/live_dev_2afc.json --activate
```]

*Example workflow (2AFC, mixed 70/30):*

#command_card[```bash
python scripts/generate_dev_test.py /data/LIVE --mode 2AFC --cross-ref 0.3
python manage.py import_study scripts/live_dev_2afc.json --activate
```]

*Example workflow (2AFC, all cross-scene):*

#command_card[```bash
python scripts/generate_dev_test.py /data/LIVE --mode 2AFC --cross-ref 1.0
python manage.py import_study scripts/live_dev_2afc.json --activate
```]

With custom paths:

#command_card[```bash
python scripts/generate_dev_test.py /data/LIVE \
    --mode 2AFC \
    --csv /data/LIVE/filelist.csv \
    --outdir images/custom_set \
    --json scripts/custom_2afc.json \
    -n 30 --seed 123
```]

*Dependencies:* Requires `Pillow` (`pip install Pillow`).


=== `createsuperuser` --- Create Admin Account

#command_card[```
python manage.py createsuperuser
```]

Interactive prompt for username, email, and password.  The superuser has full access to the admin panel and the bulk-user-creation page.

=== `runserver` --- Start Development Server

#command_card[```
python manage.py runserver 0.0.0.0:8000
```]

Bind to `0.0.0.0` to allow access from other machines on the network (useful for lab testing).


#pagebreak(weak: true)


= Researcher's Guide

This section describes the full workflow for a researcher setting up and running a subjective test.

== Step 1: Installation

Ensure Python 3.11+ and Django are installed:

#command_card[```bash
cd iqa_subjective_test
pip install -r requirements.txt
python manage.py makemigrations iqa
python manage.py migrate
python manage.py createsuperuser
```]

== Step 2: Prepare Images

Place all test images (and reference images, if applicable) into the #fname(`images/`) directory.  Subdirectories are allowed:

```
images/
├── references/
│   ├── scene_01.png
│   └── scene_02.png
├── method_a/
│   ├── scene_01_q30.png
│   └── scene_02_q30.png
└── method_b/
    ├── scene_01_q50.png
    └── scene_02_q50.png
```

Supported formats: any format the browser can display (PNG, JPEG, WebP, BMP, etc.).

== Step 3: Create a Study

There are two ways to create a study.

=== Option A: JSON import (recommended for large studies)

Write a JSON file describing the study (see the `import_study` command reference above), then run:

#command_card[```bash
python manage.py import_study my_study.json --activate
```]

=== Option B: Django admin panel

+ Navigate to `http://localhost:8000/admin/`.
+ Under *IQA*, click *Images* $arrow$ *Add Image* to register each image file.
+ Click *Studies* $arrow$ *Add Study*.
+ Fill in the study name, mode, prompt, scale settings (for MOS), and sampler.
+ In the inline section at the bottom, add stimuli:
  - For MOS: set the test image and optional reference for each row.
  - For 2AFC: set image A, image B, and optional references for each row.
+ Set `is_active = True` when ready for subjects.
+ Click *Save*.

== Step 4: Create Subject Accounts

=== Option A: Bulk creation via the web interface

Navigate to `http://localhost:8000/iqa/bulk-create-users/` (superuser login required).  You can either:
- Enter specific usernames (one per line), or
- Specify a number and the system generates `user1`, `user2`, ... with random passwords.

The resulting credentials are displayed once.  #hl[Save them immediately]---passwords cannot be recovered.

=== Option B: Django admin

Navigate to `http://localhost:8000/admin/auth/user/` and add users manually.

== Step 5: Run the Test

+ Start the server: `python manage.py runserver`
+ Distribute credentials to subjects.
+ Subjects navigate to `http://<host>:8000/iqa/login/`, log in, and begin evaluating.
+ The system automatically serves stimuli according to the selected sampler and tracks progress per user.

#info_card[
  Subjects can close the browser and resume later---their progress is saved.  If a subject revisits a previously-rated stimulus, a warning is shown and re-submitting overwrites the old response.
]

== Step 6: Monitor and Export Results

=== Web viewer

Staff users (superuser or `is_staff=True`) can view responses at:

`http://localhost:8000/iqa/responses/`

Select a study from the dropdown to see a table of all responses.

=== CSV export (web)

From the response viewer page, click the *Export CSV* button.  The downloaded CSV contains:

For MOS studies:
#table(
  columns: (1fr, 1fr, 1fr, 1fr, 1fr),
  inset: 5pt,
  [`user`], [`stimulus_order`], [`image`], [`reference`], [`score`],
)

For 2AFC studies:
#table(
  columns: (1fr, 1fr, 1fr, 1fr, 1fr, 1fr, 1fr),
  inset: 5pt,
  [`user`], [`stimulus_order`], [`image_a`], [`image_b`], [`reference_a`], [`reference_b`], [`choice`],
)

The CSV can also be downloaded directly:

#command_card[```
curl http://localhost:8000/iqa/responses/export/<study_id>/
```]

=== CSV export (command line)

The `export_responses` management command provides a richer CSV that also includes the `study` name and `timestamp` columns.  See the full command reference in @export-cmd.

#command_card[```bash
python manage.py export_responses --study 3 -o results.csv
```]

== Study Configuration Reference

#table(
  columns: (1.5fr, 0.7fr, 3fr),
  inset: 6pt,
  fill: info_table_fill,
  [*Field*], [*Default*], [*Description*],
  [`name`], [---], [Display name shown to subjects on the home page.],
  [`mode`], [---], [`MOS` or `2AFC`.  Determines the evaluation interface and response type.],
  [`prompt`], [empty], [Instruction text shown above the images during evaluation.],
  [`scale_min`], [`1`], [MOS only.  Lowest score on the rating scale.],
  [`scale_max`], [`5`], [MOS only.  Highest score on the rating scale.],
  [`scale_min_label`], [`Bad`], [MOS only.  Label displayed below the lowest score button.],
  [`scale_max_label`], [`Excellent`], [MOS only.  Label displayed below the highest score button.],
  [`sampler`], [`sequential`], [One of `sequential`, `random`, `least_evaluated`.],
  [`image_sizing`], [`fit_screen`], [How images are sized in the evaluation UI.  One of `fit_screen`, `original`, `scaled`.],
  [`image_scale_factor`], [`1.0`], [Scale factor applied when `image_sizing` is `scaled`.  For example, `0.5` displays images at half their native resolution.],
  [`zoom_enabled`], [`False`], [When enabled, hovering over any image shows a magnified overlay on every image on the page, letting subjects inspect the same region across reference and test images.],
  [`zoom_factor`], [`2.0`], [Magnification factor for the zoom overlay.  Only used when `zoom_enabled` is `True`.],
  [`is_active`], [`False`], [Only active studies are visible to subjects.],
)

=== Image Sizing Modes

- *`fit_screen`* (default) --- All images (reference and test) are constrained to fit within the browser viewport.  Good for varying screen sizes and large images.
- *`original`* --- Images are displayed at their native pixel resolution.  If images are larger than the viewport, the panel scrolls.
- *`scaled`* --- Images are displayed at `native_size × image_scale_factor`.  For example, a 1024$times$768 image with factor 0.5 is shown as 512$times$384 pixels.  Both reference and test images are scaled by the same factor.

=== Zoom Overlay

When `zoom_enabled` is `True`, hovering the mouse over any image during evaluation displays a magnified overlay on *every* image on the page simultaneously.  This allows subjects to inspect the same spatial region across reference and test images at once.

- The overlay is 1/3 of the image width by 1/3 of the image height.
- The magnification level is controlled by `zoom_factor` (e.g., `2.0` for $2 times$ zoom, `4.0` for $4 times$).
- The overlay is positioned at the corner of each image that is farthest from the mouse cursor, so it never obscures the area being inspected.
- Moving the mouse pans the zoomed view; moving off the image hides all overlays.


#pagebreak(weak: true)


= Subject's Guide

This section is intended to be shared with test participants.

== Logging In

+ Open the test URL provided by the researcher in your browser (e.g., `http://192.168.1.10:8000/iqa/login/`).
+ Enter the *username* and *password* you were given.
+ Click *Log In*.

== Home Page

After logging in, you will see a list of available studies.  Each study card shows:
- The study name.
- The evaluation type (Mean Opinion Score or Two-Alternative Forced Choice).
- An optional instruction text.

Click *Start Evaluation* on the study you wish to participate in.

== MOS Evaluation (Single Image Rating)

You will see one or two images on the screen:

- If a *reference image* is provided, it appears on the *left* side, labelled "Reference".  The image you are rating appears on the *right*, labelled "Test Image".
- If there is no reference, only the test image is shown.

Below the images is a *rating scale* (typically 1 to 5).  The endpoints are labelled (e.g., "Bad" and "Excellent").

+ Look at the image(s) carefully.
+ Click the score button that best reflects your quality assessment.
+ Click *Submit*.

The system automatically advances to the next image.

#info_card[
  A progress counter (e.g., "3 / 20") is shown in the top-right corner so you know how many images remain.
]

*Keyboard shortcuts* (button-based scoring with values 1--9 only):
- Press a *number key* (`1`--`9`) to select the corresponding score.
- Press *Enter* to submit.
When using the text-box input variant, you can type a score directly and press *Enter* to submit.

== 2AFC Evaluation (Pair Comparison)

You will see two images displayed side by side, labelled *Image A* (left) and *Image B* (right).

- If reference images are provided, they appear above their corresponding test images.
- If both images share the same reference, it is shown once at the top.

+ Compare the two images.
+ Click *Choose A* or *Choose B* to indicate which image you think has better quality.
+ Click *Submit*.

The system automatically advances to the next pair.

*Keyboard shortcuts:*
- Press *A* or *1* to select Image A.
- Press *B* or *2* to select Image B.
- Press *Enter* to submit.

== General Tips

- *Take your time.*  There is no time limit per image.
- *Neutral background.*  Images are displayed on a neutral grey background to avoid colour bias---this is intentional.
- *Zoom overlay.*  Some studies enable a zoom feature.  When available, hover your mouse over any image to see a magnified inset on each image.  The inset tracks your cursor position, so you can compare fine details across reference and test images at the same time.  Moving the mouse away from the image hides the overlay.
- *You can take breaks.*  Close the browser at any time; your progress is saved.  When you return and log in again, click "Start Evaluation" and you will continue from where you left off.
- *Changing your mind.*  If you return to a previously-rated stimulus, a warning appears.  You can submit a new response and it will replace the old one.
- *Completion.*  When all stimuli in a study have been rated, you will see a "All Done!" message.  You can then return to the home page.

== Logging Out

Click the *Logout* button on the home page when you are finished.

== Additional Instructions for Subject Running the Server on their Own Machine


To start the server, open a terminal, navigate to the `iqa_subjective_test/` directory, and run:
```bash
python manage.py runserver
```

After finishing the evaluation, please export your responses to a CSV file.  Either by clicing on the "Export" button or using the following command:
```
python manage.py export_responses -s <study-name> -o res.csv
```

For the first internal test, study name is `"ADP train_2000 (2AFC)"`



#pagebreak(weak: true)


= URL Reference

All URLs are prefixed with `/iqa/`.

#table(
  columns: (2.5fr, 1fr, 3fr),
  inset: 6pt,
  fill: info_table_fill,
  [*URL Pattern*], [*Method*], [*Description*],
  [`/iqa/`], [GET], [Redirects to `/iqa/home/`.],
  [`/iqa/home/`], [GET], [Lists active studies. Requires login.],
  [`/iqa/login/`], [GET/POST], [Login page.],
  [`/iqa/logout/`], [POST], [Logs the user out.],
  [`/iqa/next-stimulus/`], [POST], [Picks the next stimulus via sampler; redirects to the evaluation page.],
  [`/iqa/evaluate/mos/<study_id>/<stimulus_id>/`], [GET], [MOS evaluation page for a specific stimulus.],
  [`/iqa/evaluate/pair/<study_id>/<stimulus_id>/`], [GET], [2AFC evaluation page for a specific stimulus.],
  [`/iqa/submit/`], [POST], [Receives the evaluation form submission.],
  [`/iqa/bulk-create-users/`], [GET/POST], [Bulk user creation (superuser only).],
  [`/iqa/user-creation-results/`], [GET], [Shows credentials of just-created users.],
  [`/iqa/responses/`], [GET], [Response viewer with study filter (staff only).],
  [`/iqa/responses/export/<study_id>/`], [GET], [CSV download of all responses for a study (staff only).],
)
