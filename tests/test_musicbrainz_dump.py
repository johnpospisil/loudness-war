from lw.ingest.musicbrainz_dump import columns

SQL = """
CREATE TABLE release_country ( -- replicate (verbose)
    release             INTEGER NOT NULL,  -- PK, references release.id
    country             INTEGER NOT NULL,  -- PK, references country_area.area
    date_year           SMALLINT,
    date_month          SMALLINT,
    date_day            SMALLINT
);

CREATE TABLE label ( -- replicate (verbose)
    id                  SERIAL,
    gid                 UUID NOT NULL,
    name                VARCHAR NOT NULL,
    end_date_day        SMALLINT,
    ended               BOOLEAN NOT NULL DEFAULT FALSE
      CONSTRAINT label_ended_check CHECK (
        (
          -- If any end date fields are not null, then ended must be true
          (end_date_year IS NOT NULL OR
           end_date_day IS NOT NULL) AND
          ended = TRUE
        ) OR (
          (end_date_year IS NULL AND
           end_date_day IS NULL)
        )
      ),
    comment             VARCHAR(255) NOT NULL DEFAULT ''
);
"""


def test_columns_simple():
    assert columns("release_country", SQL) == [
        "release", "country", "date_year", "date_month", "date_day",
    ]  # fmt: skip


def test_columns_skip_multiline_check_constraint():
    assert columns("label", SQL) == ["id", "gid", "name", "end_date_day", "ended", "comment"]
