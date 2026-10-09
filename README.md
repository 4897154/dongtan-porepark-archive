# 동탄 포레파크 자연앤 푸르지오 공사진행 아카이브

## 초보자용 설치 방법

1. GitHub에 로그인합니다.
2. 오른쪽 위 `+` → `New repository`를 누릅니다.
3. Repository 이름을 예: `dongtan-porepark-archive` 로 정합니다.
4. `Public`을 선택하고 `Create repository`.
5. 이 ZIP의 압축을 풉니다.
6. GitHub 저장소 화면에서 `Add file` → `Upload files`.
7. 압축을 푼 폴더 안의 파일/폴더를 모두 드래그해서 올립니다.
8. `Commit changes`를 누릅니다.

## 자동 업데이트

`.github/workflows/update.yml`이 하루 한 번 PRUGIO의 고정 진입 페이지
`https://www.prugio.com/construction/construction-view.aspx?Pkey=1077`
를 확인합니다.

현재 페이지에서 새로운 `bbsNo`의 공사진행 게시물을 발견하면:
- 새 게시물 URL 확인
- 해당 게시물의 `/aptimage/` 이미지 저장
- `archive.json`에 월/BBSno/원문 URL 추가
- GitHub에 자동 commit

기존 BBSno는 다시 저장하지 않습니다.

## GitHub Pages

저장소에서 `Settings` → `Pages`로 들어갑니다.

`Build and deployment`에서:
- Source: `Deploy from a branch`
- Branch: `main`
- Folder: `/ (root)`

저장하면 GitHub가 주소를 만들어 줍니다.

## 처음에는 수동 테스트 권장

`Actions` → `Update PRUGIO construction archive` → `Run workflow`를 눌러 실행합니다.

실행 결과에서 `No new BBSno`가 나오면 정상적으로 기존 게시물을 확인한 것입니다.

주의:
PRUGIO 사이트 구조가 변경되면 자동 수집 코드의 수정이 필요할 수 있습니다.
