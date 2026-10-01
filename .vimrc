" Use Vim defaults before applying custom settings and mappings.
set nocompatible

" This file and its PT-PT mappings are UTF-8, including on older systems.
if has('multi_byte')
  set encoding=utf-8
endif
scriptencoding utf-8

" Configure the leader key with ç and 
" use it to access {[]}
let mapleader ="ç"
inoremap <Leader>0 }
inoremap <Leader>9 ]
inoremap <Leader>8 [
inoremap <Leader>7 {
" save and quit
noremap <Leader>w :w<CR>
noremap <Leader>q :q<CR>
" . should be more accessible
noremap < .
"indenting
noremap H <<
noremap L >>
" use jk to navigate sentences
noremap J )
noremap K (
" not to lose J/K 
noremap <Leader>j J
noremap <Leader>k K
"Use space start a command 
nmap <Space> :
" Make j/k work just through display lines and center screen
noremap j gj
noremap k gk
" Search / and :noh 
noremap <CR> /
noremap <C-H> :noh<CR>
noremap <Leader>h :noh<CR>
"angular brackets
imap <Leader>a {{
imap <Leader>A }}
"brackets
imap <Leader>f { }<Esc>hr<cr>O
imap <Leader>' ['']<Esc>hi
imap <Leader>( ()<Esc>i
imap <Leader>$ ${}<Esc>i
"change inside {}
noremap <Leader>i0 ci}
"select written line
noremap <Leader>v ^v$

"Use same clipboard as macOS/Linux
if has('clipboard')
  if has('unnamedplus')
    set clipboard=unnamed,unnamedplus
  else
    set clipboard=unnamed
  endif
endif
"add /g to every replacement by default
set gdefault
" Better command-line completion
set wildmenu
" Show partial commands in the last line of the screen
set showcmd
" Highlight searches (use <C-H> or <Leader>h to clear highlighting)
set hlsearch
set incsearch
set ignorecase
set smartcase
" Allow backspacing over autoindent, line breaks and start of insert action
set backspace=indent,eol,start
" Instead of failing a command because of unsaved changes, instead raise a
" dialogue asking if you wish to save changed files.
set confirm
" Display absolute + relative line numbers
set number
set relativenumber
highlight LineNr ctermfg=grey
" set indent size
set expandtab
set shiftwidth=4
set tabstop=4

"built-in Ctrl-N autocomplete
imap <Leader>n <C-n>
"imap <Tab> <C-n>

"emmet
"imap <Leader>y <C-y>,

"show highlight on the line with insert mode
augroup insert_cursorline
  autocmd!
  autocmd InsertEnter * set cul
  autocmd InsertLeave * set nocul
augroup END

" Match-it already comes with vim macros, just run it
ru macros/matchit.vim

syntax on
filetype plugin indent on

" Spell checking: only visually flag actual misspellings.
" Capitalization, rare words, and regional variants are not highlighted.
highlight! link SpellCap Normal
highlight! link SpellRare Normal
highlight! link SpellLocal Normal

" Markdown / prose reading and editing
augroup markdown_reading
  autocmd!

  " Soft wrapping only: this never inserts line breaks into the file.
  autocmd FileType markdown setlocal wrap
  autocmd FileType markdown setlocal linebreak
  autocmd FileType markdown setlocal nolist
  autocmd FileType markdown setlocal textwidth=0
  autocmd FileType markdown setlocal formatoptions-=t

  if exists('+breakindent')
    autocmd FileType markdown setlocal breakindent
  endif

  if has('spell')
    autocmd FileType markdown setlocal spelllang=en_us
    autocmd FileType markdown setlocal spell
  endif

  autocmd FileType markdown setlocal colorcolumn=
  autocmd FileType markdown setlocal foldlevel=99

  if has('conceal')
    autocmd FileType markdown setlocal conceallevel=2
    autocmd FileType markdown setlocal concealcursor=nc
  endif

  if exists('+signcolumn')
    autocmd FileType markdown setlocal signcolumn=no
  endif
augroup END

" ---- netrw ----
let g:netrw_banner = 0               " hide the header
let g:netrw_liststyle = 3            " tree view by default
let g:netrw_browse_split = 3         " open files in a new tab
let g:netrw_altv = 1                 " vertical splits open to the right
let g:netrw_winsize = 25             " 25% width when used as a sidebar
" ---- netrw keybindings ----
augroup netrw_mappings
  autocmd!
  autocmd FileType netrw call s:NetrwMappings()
augroup END
function! s:NetrwMappings()
  " yazi-style navigation
  if !empty(maparg('<Plug>NetrwLocalBrowseCheck', 'n'))
    nmap <buffer> l <Plug>NetrwLocalBrowseCheck
  else
    " Older netrw (including v149) maps Enter directly, without this <Plug>.
    " Preserve its script ID when copying the action before Enter becomes search.
    let l:open = maparg('<CR>', 'n', 0, 1)
    if get(l:open, 'buffer', 0) && get(l:open, 'rhs', '') =~# 'netrw#LocalBrowseCheck'
      let l:rhs = substitute(l:open.rhs, '\c<SID>', '<SNR>' . l:open.sid . '_', 'g')
      execute 'nnoremap <buffer> <silent> l ' . l:rhs
    endif
  endif
  nmap <buffer> h -
  nmap <buffer> . gh
  " Enter starts search, as it does elsewhere in Vim.
  nnoremap <buffer> <CR> /
  " disable destructive actions
  nnoremap <buffer> D :echo "vimrc set up for read only"<CR>
  nnoremap <buffer> R :echo "vimrc set up for read only"<CR>
  nnoremap <buffer> d :echo "vimrc set up for read only"<CR>
  nnoremap <buffer> % :echo "vimrc set up for read only"<CR>
  nnoremap <buffer> mm :echo "vimrc set up for read only"<CR>
  nnoremap <buffer> mc :echo "vimrc set up for read only"<CR>
  nnoremap <buffer> mx :echo "vimrc set up for read only"<CR>
endfunction

" Open lazygit in netrw's directory, or beside the current file.
" For an unnamed buffer, use Vim's current working directory.
function! s:CurrentDir()
  if &filetype ==# 'netrw' && exists('b:netrw_curdir')
    return b:netrw_curdir
  endif

  let l:path = expand('%:p')
  if l:path !=# ''
    if isdirectory(l:path)
      return l:path
    endif
    return fnamemodify(l:path, ':h')
  endif

  return getcwd()
endfunction

function! s:LazyGit()
  if !executable('lazygit')
    echohl WarningMsg
    echom 'lazygit not found in $PATH'
    echohl None
    return
  endif

  execute 'silent !cd ' . shellescape(s:CurrentDir()) . ' && lazygit'
  redraw!
endfunction

nnoremap <silent> <Leader>g :call <SID>LazyGit()<CR>

function! ToggleSlashComment() range
  " Look at the first selected line to decide direction
  let l:line = getline(a:firstline)
  if l:line =~ '^\s*//'
    " Uncomment: remove the first // and one optional following space
    execute a:firstline . ',' . a:lastline . 's:^\(\s*\)// \?:\1:'
  else
    " Comment: insert // after the leading whitespace
    execute a:firstline . ',' . a:lastline . 's:^\(\s*\):\1// :'
  endif
  nohlsearch
endfunction

xnoremap <silent> <Leader>c :call ToggleSlashComment()<CR>
