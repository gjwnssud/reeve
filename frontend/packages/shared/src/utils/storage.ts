export const STORAGE_KEYS = {
  theme: 'reeve-theme',
  clientUUID: 'reeve_client_uuid',
  fileStats: (uuid: string) => `reeve_file_stats_${uuid}`,
  folderStats: (uuid: string) => `reeve_folder_stats_${uuid}`,
  serverStats: (uuid: string) => `reeve_server_stats_${uuid}`,
} as const;
