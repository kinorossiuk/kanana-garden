package dev.kinorossiuk.kananagarden.bridge;

import android.content.ContentProvider;
import android.content.ContentValues;
import android.database.Cursor;
import android.database.MatrixCursor;
import android.net.Uri;
import android.os.ParcelFileDescriptor;
import android.provider.OpenableColumns;

import java.io.File;
import java.io.FileNotFoundException;
import java.io.IOException;

/** Read-only, single-file provider used only for the verified OTA APK. */
public final class UpdateFileProvider extends ContentProvider {
    private static final String FILE_NAME = "kanana-update.apk";
    private static final String URI_PATH = "/" + FILE_NAME;

    @Override
    public boolean onCreate() {
        return true;
    }

    @Override
    public String getType(Uri uri) {
        requireUpdateUri(uri);
        return "application/vnd.android.package-archive";
    }

    @Override
    public Cursor query(
            Uri uri,
            String[] projection,
            String selection,
            String[] selectionArgs,
            String sortOrder
    ) {
        File file = requireUpdateFile(uri);
        String[] columns = projection == null
                ? new String[]{OpenableColumns.DISPLAY_NAME, OpenableColumns.SIZE}
                : projection;
        MatrixCursor cursor = new MatrixCursor(columns, 1);
        MatrixCursor.RowBuilder row = cursor.newRow();
        for (String column : columns) {
            if (OpenableColumns.DISPLAY_NAME.equals(column)) {
                row.add(FILE_NAME);
            } else if (OpenableColumns.SIZE.equals(column)) {
                row.add(file.length());
            } else {
                row.add(null);
            }
        }
        return cursor;
    }

    @Override
    public ParcelFileDescriptor openFile(Uri uri, String mode) throws FileNotFoundException {
        if (!"r".equals(mode)) {
            throw new FileNotFoundException("OTA APK is read-only");
        }
        return ParcelFileDescriptor.open(requireUpdateFile(uri), ParcelFileDescriptor.MODE_READ_ONLY);
    }

    @Override
    public Uri insert(Uri uri, ContentValues values) {
        throw new UnsupportedOperationException("read-only provider");
    }

    @Override
    public int delete(Uri uri, String selection, String[] selectionArgs) {
        throw new UnsupportedOperationException("read-only provider");
    }

    @Override
    public int update(Uri uri, ContentValues values, String selection, String[] selectionArgs) {
        throw new UnsupportedOperationException("read-only provider");
    }

    static File updateFile(android.content.Context context) {
        return new File(new File(context.getCacheDir(), "updates"), FILE_NAME);
    }

    static Uri updateUri(android.content.Context context) {
        return new Uri.Builder()
                .scheme("content")
                .authority(context.getPackageName() + ".updates")
                .path(FILE_NAME)
                .build();
    }

    private void requireUpdateUri(Uri uri) {
        String expectedAuthority = getContext() == null
                ? "" : getContext().getPackageName() + ".updates";
        if (!"content".equals(uri.getScheme())
                || !expectedAuthority.equals(uri.getAuthority())
                || !URI_PATH.equals(uri.getPath())) {
            throw new IllegalArgumentException("unknown OTA content URI");
        }
    }

    private File requireUpdateFile(Uri uri) {
        requireUpdateUri(uri);
        if (getContext() == null) {
            throw new IllegalStateException("provider context unavailable");
        }
        File file = updateFile(getContext());
        try {
            File directory = new File(getContext().getCacheDir(), "updates").getCanonicalFile();
            File expected = file.getCanonicalFile();
            if (!directory.equals(expected.getParentFile()) || !expected.isFile()) {
                throw new IllegalArgumentException("verified OTA APK is unavailable");
            }
            return expected;
        } catch (IOException error) {
            throw new IllegalArgumentException("invalid OTA APK path", error);
        }
    }
}
