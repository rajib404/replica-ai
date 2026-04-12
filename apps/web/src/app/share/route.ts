import { NextResponse, type NextRequest } from 'next/server';

// Web Share Target POST handler.
//
// Receives shared content (text, URLs, files) from the host OS share sheet
// and forwards it to the dashboard. For text/URL shares we redirect to the
// chat with the content pre-filled. For file shares we forward the files to
// the FastAPI knowledge ingestion endpoint, then redirect to the knowledge
// page.
//
// The PWA manifest declares this endpoint in `share_target.action`.

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

export async function POST(request: NextRequest): Promise<NextResponse> {
  let formData: FormData;
  try {
    formData = await request.formData();
  } catch {
    return NextResponse.redirect(new URL('/dashboard/chat', request.url), 303);
  }

  const title = (formData.get('title') as string | null) ?? '';
  const text = (formData.get('text') as string | null) ?? '';
  const url = (formData.get('url') as string | null) ?? '';
  const files = formData.getAll('files').filter((f): f is File => f instanceof File);

  if (files.length > 0) {
    // Forward files to the backend knowledge ingestion endpoint. We forward
    // the auth cookie if present so the backend can attribute uploads.
    const cookie = request.headers.get('cookie') ?? '';
    const failures: string[] = [];

    for (const file of files) {
      const upload = new FormData();
      upload.append('file', file, file.name);
      if (title) upload.append('title', title);
      if (text) upload.append('description', text);

      try {
        const resp = await fetch(`${API_URL}/api/knowledge/upload`, {
          method: 'POST',
          headers: cookie ? { cookie } : undefined,
          body: upload,
        });
        if (!resp.ok) {
          failures.push(file.name);
        }
      } catch {
        failures.push(file.name);
      }
    }

    const dest = new URL('/dashboard/knowledge', request.url);
    dest.searchParams.set('shared', 'files');
    dest.searchParams.set('count', String(files.length - failures.length));
    if (failures.length > 0) {
      dest.searchParams.set('failed', String(failures.length));
    }
    return NextResponse.redirect(dest, 303);
  }

  // Text / URL share — pre-fill the chat input.
  const dest = new URL('/dashboard/chat', request.url);
  const combined = [title, text, url].filter(Boolean).join('\n');
  if (combined) {
    dest.searchParams.set('shared', combined);
  }
  return NextResponse.redirect(dest, 303);
}

export async function GET(request: NextRequest): Promise<NextResponse> {
  // Some platforms send GET share targets for text/URL only.
  const { searchParams } = new URL(request.url);
  const title = searchParams.get('title') ?? '';
  const text = searchParams.get('text') ?? '';
  const url = searchParams.get('url') ?? '';

  const dest = new URL('/dashboard/chat', request.url);
  const combined = [title, text, url].filter(Boolean).join('\n');
  if (combined) {
    dest.searchParams.set('shared', combined);
  }
  return NextResponse.redirect(dest, 303);
}
