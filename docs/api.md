# Python API

The names documented here are exported from `ssmdconvert` and listed in `ssmdconvert.__all__`.

## Conversion

```{autofunction} ssmdconvert.convert
```

```{autoclass} ssmdconvert.Converter
:members:
```

```{autoclass} ssmdconvert.ConversionResult
:members:
```

## Source-neutral models

```{autoclass} ssmdconvert.SourceInfo
:members:
```

```{autoclass} ssmdconvert.Section
:members:
```

```{autoclass} ssmdconvert.Document
:members:
```

## Books and chapters

```{autoclass} ssmdconvert.Book
:members:
```

```{autoclass} ssmdconvert.BookChapter
:members:
```

```{autoclass} ssmdconvert.BookInspection
:members:
```

```{autoclass} ssmdconvert.BookInspectionChapter
:members:
```

```{autofunction} ssmdconvert.inspect_book
```

```{autofunction} ssmdconvert.convert_book
```

```{autofunction} ssmdconvert.parse_chapter_selection
```

## Bundles

```{autofunction} ssmdconvert.write_book_bundle
```

```{autofunction} ssmdconvert.load_book_bundle
```

```{autofunction} ssmdconvert.validate_book_bundle
```

## Errors

```{autoclass} ssmdconvert.BookError
```

```{autoclass} ssmdconvert.UnsupportedBookSourceError
```

```{autoclass} ssmdconvert.ChapterSelectionError
```

```{autoclass} ssmdconvert.BookBundleError
```

```{autoclass} ssmdconvert.BookBundleValidationError
```


## Version

```{autodata} ssmdconvert.__version__
```
