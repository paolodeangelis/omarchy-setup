# Olio su Silicio backgrounds

Each wallpaper image must have a same-stem JSON file. Theme activation validates
the pair before changing the desktop. Omarchy discovers the image itself, so a
new valid pair automatically joins the background chooser and rotation.

Required JSON fields are `schema_version` (currently `1`), `title`, `artist`,
`date`, `medium`, `collection`, `source_name`, `source_url`, `rights`, and
`identification` (`verified` or `unverified`). Optional translated or original
titles may be added as `title_en` and `title_original`.

Do not guess an attribution. Use `unverified` until the image is matched to a
reliable museum, auction, catalogue, or collection source.

The Olio shell shows the current record from a padded `i` button at the
bottom-right of each display and advances to the next background every 24
hours while the shell session remains running.
